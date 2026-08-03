# Swap Hooks Experiments

> this repo uses
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13)

### Install and Setup

you have to install:

- python package manager: [uv](https://docs.astral.sh/uv/);
- python linter and formatter: [ruff](https://github.com/astral-sh/ruff) ;
- node js for code linting and formatting:
  [node](https://nodejs.org/en/download);

than run:

1. `npm install` to install all the node stuff;
2. `uv venv` to create a python virtual environment;
3. `uv sync` to sync all deps;

### Dev Guide

- _Format_: via `npm run format`;
- _Add dependency_: via `uv add <DEP_NAME>`;
- _Mirror pip_: `pip ...` is equivalent to `uv pip ...`;

### Useful Links

- @TODO:
