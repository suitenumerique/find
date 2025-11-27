# Search Engine Evaluation Command

## Overview 

this Django command atomizes the evaluation of the search engine by computing 4 metrics: Average Discounted Cumulative Gain, Precision, Recall and F1 score. 

## Usage 

```
python manage.py evaluate_search_engine <dataset_name> [options]
```

## Required Arguments
- `dataset_name`: Name of the evaluation dataset to use. Datasets are located in `evaluation/management/commands/data/evaluation/`

## Optional Arguments
- `--min_score`: Minimum score threshold; hits below this score are ignored
- `--keep-index`: Preserve the evaluation index after completion
- `--force-reindex`: Drop and recreate the index even if it exists

## Examples

````
# Basic evaluation with default settings
python manage.py evaluate_search_engine my_dataset

# Evaluation with minimum score threshold
python manage.py evaluate_search_engine my_dataset --min_score 0.5

# Force reindexing and clean up afterward
python manage.py evaluate_search_engine my_dataset --force-reindex True --keep-index False
````
