import os
import string
import subprocess
from pathlib import Path

import networkx as nx  # NetworkX
import nltk  # NLTK
import yaml  # PyYAML

nltk.download('punkt')

with open('./consts/db.csv') as db_file:
    dbs = [db.lower() for db in db_file.read().splitlines()]
with open('./consts/bus.csv') as bus_file:
    buses = [bus.lower() for bus in bus_file.read().splitlines()]
with open('./consts/lang.csv') as lang_file:
    langs = [lang.lower() for lang in lang_file.read().splitlines()]
with open('./consts/server.csv') as server_file:
    servers = [server.lower() for server in server_file.read().splitlines()]
with open('./consts/gateway.csv') as gate_file:
    gates = [gate.lower() for gate in gate_file.read().splitlines()]
with open('./consts/monitor.csv') as monitor_file:
    monitors = [monitor.lower() for monitor in monitor_file.read().splitlines()]
with open('./consts/discovery.csv') as disco_file:
    discos = [disco.lower() for disco in disco_file.read().splitlines()]

DATA = {
    'dbs': dbs, 'servers': servers, 'buses': buses, 'langs': langs, 'gates': gates, 'monitors': monitors, 'discos': discos
}


def get_words(data, unique=False):
    data = data.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
    data = data.translate(str.maketrans(string.digits, ' ' * len(string.digits)))
    data = data.lower()
    words = [w for w in nltk.word_tokenize(data) if len(w) > 2]
    if unique:
        words = set(words)
    return words


def are_similar(name, candidate):
    return name == candidate


def match_one(name, l):
    for candidate in l:
        if are_similar(name, candidate):
            return [candidate]
    return []


def match_ones(names, l):
    for name in names:
        res = match_one(name, l)
        if res:
            return res
    return []


def check_shared_db(analysis):
    db_services = set(analysis['detected_dbs']['services'])
    dependencies = []
    for service in analysis['services']:
        dependencies += set(service['depends_on']) & db_services
    return len(set(dependencies)) != len(dependencies)


def analyze_docker_compose(workdir, dc):
    print('-analyzing docker-compose')
    dep_graphs = {'full': nx.DiGraph(), 'micro': None}
    nodes_not_microservice = []
    analysis = {'path': dc, 'num_services': 0, 'services': [], 'detected_dbs': { 'num' : 0, 'names': [], 'services': [], 'shared_dbs' : False} }
    with open(workdir+dc) as f:
        try:
            data = yaml.load(f, Loader=yaml.FullLoader)
            services = []
            detected_dbs = []
            if not data or 'services' not in data or not data['services']:
                return analysis
            for name, service in data['services'].items():
                if not service:
                    continue
                s = {}
                s['name'] = name
                if 'image' in service and service['image']:
                    s['image'] =  service['image'].split(':')[0]
                    s['image_full'] =  service['image']
                elif 'build' in service and service['build']:
                    s['image'] = s['image_full'] = service['build']
                else:
                    s['image'] = s['image_full'] =  ''
                if isinstance(s['image'], dict):
                    s['image'] = s['image_full'] =  str(list(s['image'].values())[0])

                for k,v in DATA.items():
                    if k == 'langs':
                        continue
                    s[k] = match_ones(get_words(s['image']), v)

                if s['dbs']:
                    detected_dbs.append({'service' : name, 'name': s['dbs'][0]})

                if 'depends_on' in service:
                    if isinstance(service['depends_on'], dict):
                        s['depends_on'] = list(service['depends_on'].keys())
                    else:
                        s['depends_on'] = service['depends_on']
                elif 'links' in service:
                    s['depends_on'] = list(service['links'])
                else:
                    s['depends_on'] = []
                services.append(s)

                # add the node to the dependencies graph
                dep_graphs['full'].add_node(name)
                # add the edges to the dependencies graph
                dep_graphs['full'].add_edges_from([(name, serv) for serv in s['depends_on']])
                # append the node to the nodes_not_microservice list if the node is not a microservice
                if s['dbs'] or s['servers'] or s['buses'] or s['gates'] or s['monitors'] or s['discos']:
                    nodes_not_microservice.append(name)
            analysis['services'] = services
            analysis['num_services'] = len(services)
            analysis['detected_dbs'] = {'num': len(detected_dbs), \
                                        'names' : list({db['name'] for db in detected_dbs}), \
                                        'services' : [db['service'] for db in detected_dbs]}
            analysis['detected_dbs']['shared_dbs'] = check_shared_db(analysis)

            # copy the full graph
            dep_graphs['micro'] = dep_graphs['full'].copy()
            # delete the not-microservice nodes from the micro dependencies graph
            for node in nodes_not_microservice:
                dep_graphs['micro'].remove_node(node)
            for g in dep_graphs:
                analysis['dep_graph_' + g] = {'nodes': dep_graphs[g].number_of_nodes(),
                                              'edges': dep_graphs[g].number_of_edges(),
                                              'avg_deps_per_service': dep_graphs[g].number_of_nodes() and sum([out_deg for name, out_deg in dep_graphs[g].out_degree]) / dep_graphs[g].number_of_nodes() or 0,
                                              'acyclic': nx.is_directed_acyclic_graph(dep_graphs[g]),
                                              'longest_path': nx.dag_longest_path_length(dep_graphs[g]) if nx.is_directed_acyclic_graph(dep_graphs[g]) else 'inf'}

        except (UnicodeDecodeError, yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
            print(e)

    return analysis


def locate_files(workdir, filename):
    print('-locating ', filename)
    res = []
    try:
        for df in Path(workdir).rglob(filename):
            if not df.is_file():
                continue
            df = str(df)
            res.append(df.split(workdir)[-1])
    except OSError:
        pass
    return res
