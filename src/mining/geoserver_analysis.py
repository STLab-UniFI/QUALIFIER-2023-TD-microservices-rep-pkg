"""
This script performs a commit-by-commit analysis on the Geoserver Cloud repository
(https://github.com/geoserver/geoserver-cloud). It traverses all the commits of main branch running two analysis: the
first with the function from Baresi et al. for counting the number of microservices in the code, and the second with
SonarQube in order to retrieve some metric relatives to code quality/technical debt.
"""

import csv
import logging
import re
import time
from datetime import timedelta
from pathlib import Path

import git  # GitPython
from pydriller import Repository  # PyDriller

from microservices_analysis import analyze_docker_compose, locate_files
from print_utils import print_progress, print_major_step, print_minor_step, print_info, block_print, restore_print
from repo import clear_repo
from sonarqube import sq_start_up, sq_shut_down, sq_post, sq_measure, sq_scanner_geoserver, sq_wait_ce

SQ_METRICS = ["COMPLEXITY", "COGNITIVE_COMPLEXITY",  # complexity
              "VIOLATIONS",  # issues
              "BLOCKER_VIOLATIONS", "CRITICAL_VIOLATIONS", "MAJOR_VIOLATIONS", "MINOR_VIOLATIONS", "INFO_VIOLATIONS",
              "CODE_SMELLS", "SQALE_RATING", "SQALE_INDEX", "SQALE_DEBT_RATIO",  # maintainability
              "ALERT_STATUS",  # quality gate
              "BUGS", "RELIABILITY_RATING", "RELIABILITY_REMEDIATION_EFFORT",  # reliability
              "VULNERABILITIES", "SECURITY_RATING", "SECURITY_REMEDIATION_EFFORT", "SECURITY_HOTSPOTS",  # security
              "CLASSES", "COMMENT_LINES", "COMMENT_LINES_DENSITY", "DIRECTORIES", "FILES",  # size
              "LINES", "NCLOC", "FUNCTIONS", "STATEMENTS"
              ]

DS_KEYS = ["REPO", "COMMIT",  # identifier
           "AUTHOR_NAME", "AUTHOR_EMAIL", "AUTHOR_DATE", "AUTHORS",  # author info
           "COMMITTER_NAME", "COMMITTER_EMAIL", "COMMITTER_DATE", "COMMITTERS",  # committer info
           "MICROSERVICES"  # microservices
           ] + SQ_METRICS


def analyze_repo(url: str, repo_writer: csv.DictWriter, recurse: bool = False) -> None:
    """
    Run the analysis of a single repo

    :param url: url of the repository
    :param repo_writer: CSV writer to write the results of analysis at dataset level
    :param recurse: if True the cloning recurse on the submodules
    :return: None
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'# Start repo analysis ({name}) [{url}]')
    workdir = 'temp/clones/' + name

    try:
        print_info('  Cloning repo and creating SQ project')
        repository = Repository(url + ".git")  # Pydriller: useful to traverse commits history
        git_repo = git.Repo.clone_from(url, workdir)  # GitPython: useful to work with repo (git show, shortlog...)

        sq_post('api/projects/create', {'name': name, 'project': name})

        print_info('  Counting commits')
        num_of_commits = len(list(repository.traverse_commits()))

        count = 0
        for commit in repository.traverse_commits():  # Apparently traverse_commits traverses only main branch commits
            count += 1
            print_minor_step(f'  Start commit analysis ({count}/{num_of_commits}) [{commit.hash}]')

            git_repo.git.checkout(commit.hash, force=True)

            if recurse:
                gitmodules_file = Path(__file__).parent.joinpath(f'temp/clones/{name}/.gitmodules')
                if gitmodules_file.exists():
                    # To avoid cloning through ssh, which require authentication, all modules are updated so they can be
                    # cloned through https
                    with open(gitmodules_file, 'r') as gitmodules:
                        gitmodules_content = gitmodules.read()
                    gitmodules_content = re.sub("git@github.com:", "https://github.com/", gitmodules_content)
                    with open(gitmodules_file, 'w') as gitmodules:
                        gitmodules.write(gitmodules_content)

                try:
                    git_repo.git.execute(['git', 'submodule', 'update', '--init', '--recursive'])
                except Exception as e_submodules:
                    logging.error('Error updating submodules', exc_info=e_submodules)

            repo_analysis: dict[str, str | int | None] = dict.fromkeys(DS_KEYS)

            repo_analysis['REPO'] = url
            repo_analysis['COMMIT'] = commit.hash

            print_info('  Analyzing Git history')
            recover_git_infos(git_repo, commit.hash, repo_analysis)

            print_info('  Analyzing microservices')
            compute_microservice_metric(workdir, repo_analysis)

            print_info('  Analyzing SonarQube code quality')
            mvn_success = sq_scanner_geoserver(name)

            if mvn_success:
                print_info('  Waiting results\' availability and retrieving metrics\' measures')
                if sq_wait_ce(name):
                    retrieve_sq_metrics(name, repo_analysis)

            print_info('  Writing data')
            repo_writer.writerow(repo_analysis)
    except Exception:
        raise
    finally:
        print_info('  Clearing temporary directories')
        clear_repo(Path(workdir))


def compute_microservice_metric(workdir: str, analysis: dict[str, str | int | None]) -> None:
    """
    Performs the analysis of the repository with Baresi et al. script and select the resulting number of microservices

    :param workdir: directory of the repository
    :param analysis: dictionary where to save information
    :return: None
    """
    block_print()
    docker_compose = locate_files(workdir, 'docker-compose.yml') + locate_files(workdir, 'docker-compose.yaml')
    restore_print()
    if len(docker_compose):
        microservices_structure = analyze_docker_compose(workdir, docker_compose[0])
        try:
            analysis['MICROSERVICES'] = microservices_structure['dep_graph_micro']['nodes']
        except KeyError:
            analysis['MICROSERVICES'] = None
    else:
        analysis['MICROSERVICES'] = 0


def retrieve_sq_metrics(component: str, analysis: dict[str, str | int | None]) -> None:
    """
    Retrieves SonarQube metrics' measures from the SonarQube server

    :param component: project/component key
    :param analysis: dictionary where to save information
    :return: None
    """
    for metric in SQ_METRICS:
        analysis[metric] = sq_measure(component, metric.lower())


def recover_git_infos(git_repo: git.Repo, commit_hash: str, analysis: dict[str, str | int | None]) -> None:
    """
    Recovers information from the Git repository about a commit (author's name and email, committer's name and email
    and number of author and committers up to that commit)

    :param git_repo: Git repository
    :param commit_hash: Commit
    :param analysis: dictionary where to save information
    :return: None
    """
    analysis['AUTHOR_NAME'] = git_repo.git.execute(["git", "show", "-s", "--format='%an'", commit_hash])[1:-1]
    analysis['AUTHOR_EMAIL'] = git_repo.git.execute(["git", "show", "-s", "--format='%ae'", commit_hash])[1:-1]
    analysis['AUTHOR_DATE'] = git_repo.git.execute(["git", "show", "-s", "--format='%as'", commit_hash])[1:-1]
    analysis['COMMITTER_NAME'] = git_repo.git.execute(["git", "show", "-s", "--format='%cn'", commit_hash])[1:-1]
    analysis['COMMITTER_EMAIL'] = git_repo.git.execute(["git", "show", "-s", "--format='%ce'", commit_hash])[1:-1]
    analysis['COMMITTER_DATE'] = git_repo.git.execute(["git", "show", "-s", "--format='%cs'", commit_hash])[1:-1]
    analysis['AUTHORS'] = len(git_repo.git.execute(["git", "shortlog", "HEAD", "-s"]).splitlines())
    analysis['COMMITTERS'] = len(git_repo.git.execute(["git", "shortlog", "HEAD", "-s", "-c"]).splitlines())


if __name__ == "__main__":
    print_major_step(" Start script execution")
    start_time = time.time()

    print_info(' Starting up SonarQube server')
    sq_start_up()

    try:
        print_info(' Performing analysis')
        output_file = Path(__file__).parent / '../data/raw/DATASET_mining_output.csv'

        with open(output_file, 'w+', newline='') as ds_output:
            writer = csv.DictWriter(ds_output, DS_KEYS)
            writer.writeheader()

            analyze_repo('https://github.com/geoserver/geoserver-cloud', writer)
    except Exception as e:
        logging.error("Unexpected error", exc_info=e)
    finally:
        print_info(' Shutting down SonarQube server')
        sq_shut_down()

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
