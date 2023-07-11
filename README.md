# Tracing the Footsteps of Technical Debt in Microservice Architectures: A Preliminary Case Study
This repository is a companion page for the following publication:
> Verdecchia, R., Maggi, K., Scommegna, L., Enrico, V. 2023. Tracing the Footsteps of Technical Debt in Microservice Architectures: A Preliminary Case Study. Submitted for revision to the 1st International Workshop on Quality in Software Architecture (QUALIFIER)

It contains all the material required for replicating the study, including: repository mining script, mining raw data and data analysis script.

<!--

## How to cite us
The scientific article describing design, execution, and main results of this study is available [here](https://www.google.com).


If this study is helping your research, consider to cite it is as follows, thanks!

```
@article{,
  title={},
  author={},
  journal={},
  volume={},
  pages={},
  year={},
  publisher={}
}
```
-->

## Quick start
Here a documentation on how to use the replication material should be provided.

### Requirements

- Python 3.10
- Docker (Docker Engine + Docker Compose)

### Preliminary

- Clone the repo in the directory you want (we refer to it as `$CLONE_DIR`):

  ```
  git clone https://github.com/STLab-UniFI/QUALIFIER-2023-TD-microservices-rep-pkg $CLONE_DIR
  ```

- Move to [src folder](src/):

  ```
  cd $CLONE_DIR/src
  ```

### Repository mining phase

- Move to [mining folder](src/mining/):

  ```
  cd mining
  ```

- Install all the Python package required:

  ```
  pip install -r requirements.txt
  ```

- Run the script:

  ```
  python geoserver_analysis.py
  ```


  N.B. The script starts Docker containers so Docker Engine must be started and on Linux/macOS you could have to precede the commands with `sudo` if the user is not in the Docker group.

### Data analysis phase

<!-- TODO -->

## Repository Structure
This is the root directory of the repository. The directory is structured as follows:

    QUALIFIER-2023-TD-microservices-rep-pkg
     .
     |
     |--- src/                             Source code used in the paper
     |      |
     |      |--- mining/		           Scripts for the repository mining phase
     |      |
     |      |--- analysis/		           Scripts for the data analysis phase
     |
     |--- data/                            Data used in the paper 
            |
            |--- raw/     		           Results from the repository mining phase
            |
            |--- final/					   Results from the data analysis phase
## License
The source code is licensed under the MIT license, which you can find in the [LICENSE file](LICENSE).

All graphical/text assets are licensed under the [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).