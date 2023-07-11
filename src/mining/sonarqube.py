import logging
import re
import subprocess
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

import requests
from print_utils import print_appendable
from requests import RequestException
from requests.auth import HTTPBasicAuth

SQ_USER = 'admin'
SQ_PASSWORD = 'admin'  # FIXME change pw
SQ_TOKEN = ''
SQ_TOKEN_NAME = 'mining_script'  # FIXME change token name


def sq_start_up() -> None:
    """
    Starts SonarQube server with Docker compose and creates an user token

    :return: None
    """
    cmd = ['docker', 'compose', 'up']
    subprocess.Popen(cmd, cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print_appendable('Starting Docker container')
    while True:
        time.sleep(5)
        try:
            print_appendable('.')
            response = sq_get('api/system/status')
            if response['status'] == 'UP':
                print(' SonarQube is operational')
                break
        except RequestException:
            continue

    global SQ_TOKEN
    SQ_TOKEN = sq_post('api/user_tokens/generate', {'name': SQ_TOKEN_NAME})['token']


def sq_shut_down(remove: bool = False) -> None:
    """
    Shuts down SonarQube server instance (also revoking the user token)

    :param remove: if True it removes the containers
    :return: None
    """
    sq_post('api/user_tokens/revoke', {'name': SQ_TOKEN_NAME})
    global SQ_TOKEN
    SQ_TOKEN = None

    if remove:
        cmd = ['docker', 'compose', 'down']
    else:
        cmd = ['docker', 'compose', 'stop']

    subprocess.run(cmd, cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sq_token() -> str:
    """
    Returns the current user token

    :return: user token
    """
    return SQ_TOKEN


def sq_get(url: str, params: dict[str, str] = None) -> Any:
    """
    Performs a get request to SonarQube server through Web API

    :param url: API
    :param params: parameters
    :return: response
    """
    if params is None:
        params = {}
    response = requests.get('http://localhost:9000/' + url,
                            auth=HTTPBasicAuth(username=SQ_USER, password=SQ_PASSWORD),
                            verify=False,
                            params=params)
    return response.json()


def sq_post(url: str, params: dict[str, str]) -> Any:
    """
    Performs a post request to SonarQube server through Web API

    :param url: API
    :param params: parameters
    :return: response
    """
    response = requests.post('http://localhost:9000/' + url,
                             auth=HTTPBasicAuth(username=SQ_USER, password=SQ_PASSWORD),
                             verify=False,
                             params=params)
    try:
        return response.json()
    except JSONDecodeError:
        return None


def sq_scanner_geoserver(project: str, verbose: bool = False) -> bool:
    """
    Performs the Maven build with Sonar Scanner analysis

    :param project: project key on the SonarQube server
    :param verbose: if True all Maven log will be printed to the console

    :return: True if the build succeed, False otherwise. N.B. if verbose=True, the detection of build success could be
    less accurate
    """
    try:
        # In some commits it is necessary to update dependencies version or repositories url in order to allow Maven to
        # build without failure. In some commits it is also necessary to deactivate an active-by-default profile in
        # order to not include a Maven module that in the meanwhile has been included in the repository as git submodule
        # (before it was an external dependencies of Maven).
        # All these updates are made in all the commits without conflicts in those commits where they are not strictly
        # necessary.
        old_lombok_dep = "<groupId>org.projectlombok</groupId>\s*" \
                         "<artifactId>lombok</artifactId>\s*" \
                         "<version>((\$\{[a-zA-z.]*\})|[0-9.]+)</version>"
        new_lombok_dep = "<groupId>org.projectlombok</groupId>\n" \
                         "<artifactId>lombok</artifactId>\n" \
                         "<version>1.18.24</version>"
        old_lombok_var = "<lombok.version>[0-9.]+</lombok.version>"
        new_lombok_var = "<lombok.version>1.18.24</lombok.version>"
        old_spring_repo = "https://repo.spring.io/release"
        new_spring_repo = "https://repo.spring.io/milestone"
        old_gs_var = "<gs.version>2.2[0-9](.[0-9])*(-[A-Z]+)*</gs.version>"
        new_gs_var = "<gs.version>2.23.1</gs.version>"
        old_gs_com_var = "<gs.community.version>2.2[0-9](.[0-9])*(-[A-Z]+)*</gs.community.version>"
        new_gs_com_var = "<gs.community.version>2.22.0</gs.community.version>"
        old_gs_prof = "<id>geoserver</id>\s*" \
                      "<activation>\s*<activeByDefault>true</activeByDefault>\s*</activation>"
        new_gs_prof = "<id>geoserver</id>\n" \
                      "<activation>\n<activeByDefault>false</activeByDefault>\n</activation>"
        old_dep = "<groupId>org.geoserver.community</groupId>\s*" \
                  "<artifactId>gs-datadir-catalog-loader</artifactId>\s*" \
                  "<version>\$\{gs.community.version\}</version>"
        new_dep = "<groupId>org.geoserver.community</groupId>\n" \
                  "<artifactId>gs-datadir-catalog-loader</artifactId>\n" \
                  "<version>2.24-SNAPSHOT</version>"

        # The updates are necessary in the main POM and/or in the src/POM based on commits, so they are made in both
        poms_file = [Path(__file__).parent.joinpath(f'temp/clones/{project}/pom.xml'),
                     Path(__file__).parent.joinpath(f'temp/clones/{project}/src/pom.xml')]

        for pom_file in poms_file:
            if pom_file.exists():
                with open(pom_file, 'r') as pom:
                    pom_content = pom.read()

                pom_content = re.sub(old_lombok_dep, new_lombok_dep, pom_content)
                pom_content = re.sub(old_lombok_var, new_lombok_var, pom_content)
                pom_content = re.sub(old_spring_repo, new_spring_repo, pom_content)
                pom_content = re.sub(old_gs_var, new_gs_var, pom_content)
                pom_content = re.sub(old_gs_com_var, new_gs_com_var, pom_content)
                pom_content = re.sub(old_gs_prof, new_gs_prof, pom_content)
                pom_content = re.sub(old_dep, new_dep, pom_content)

                with open(pom_file, 'w') as pom:
                    pom.write(pom_content)

        # In early commits it was not present the Maven wrapper
        if not Path(Path(__file__).parent.joinpath(f'temp/clones/{project}/.mvn')).exists():
            cmd = f'mvn clean compile org.sonarsource.scanner.maven:sonar-maven-plugin:3.9.1.2184:sonar ' \
                  f'-Dsonar.host.url=http://localhost:9000 -Dsonar.login={SQ_TOKEN} -Dsonar.projectKey={project} ' \
                  '-U -B -Dmaven.compiler.failOnError=false'
        else:
            cmd = f'./mvnw clean compile org.sonarsource.scanner.maven:sonar-maven-plugin:3.9.1.2184:sonar ' \
                  f'-Dsonar.host.url=http://localhost:9000 -Dsonar.login={SQ_TOKEN} -Dsonar.projectKey={project} ' \
                  '-U -B -Dmaven.compiler.failOnError=false'

        if verbose:
            mvn = subprocess.run(cmd,
                                 cwd=Path(__file__).parent.joinpath("temp/clones/" + project),
                                 shell=True)
            return True if mvn.returncode == 0 else False
        else:
            mvn = subprocess.run(cmd,
                                 cwd=Path(__file__).parent.joinpath("temp/clones/" + project),
                                 shell=True, stdout=subprocess.PIPE, text=True)
            return True if mvn.returncode == 0 and "BUILD SUCCESS" in mvn.stdout else False

    except Exception as e:
        logging.error("Error building with Maven", exc_info=e)
        return False


def sq_wait_ce(component: str) -> bool:
    """
    Checks if the current task has finished running or not and if it has succeeded

    :param component: the component of which we are interested in task
    :return: True if task succeeds, False otherwise
    """
    while True:
        time.sleep(5)
        try:
            response = sq_get('api/ce/component', {'component': component})
            if len(response['queue']):
                print_appendable('.')
            elif response['current']['status'] == 'SUCCESS':
                print(' Processing ended')
                return True
            else:
                print(' Processing ended')
                return False
        except RequestException:
            continue


def sq_measure(component: str, metric: str) -> Optional[str | int]:
    """
    Queries the server to get the measurement of a metric

    :param component: component to which look up
    :param metric: metric to retrieve
    :return: the value of measure or None if the metric has not been calculated
    """
    # noinspection PyBroadException
    try:
        response = sq_get('api/measures/component', {'component': component, 'metricKeys': metric})
        measures = response['component']['measures']
        if not measures:
            return None

        return measures[0]['value']
    except Exception:
        return ''
