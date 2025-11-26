"""
Evaluate search engine performance with test documents and queries.
"""

import importlib
import logging
import math
import os
import time
import unicodedata

from django.conf import settings
from django.core.management.base import BaseCommand

from core.management.commands.create_search_pipeline import (
    ensure_search_pipeline_exists,
)
from core.management.commands.utils import (
    bulk_create_documents,
    delete_search_pipeline,
    prepare_index,
)
from core.services.opensearch import (
    check_hybrid_search_enabled,
    opensearch_client,
    search,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Evaluate search engine performance"""

    help = __doc__
    opensearch_client_ = opensearch_client()
    index_name = "evaluation-index"
    search_params = {
        "nb_results": 20,
        "language_code": settings.DEFAULT_LANGUAGE_CODE,
        "order_by": "relevance",
        "order_direction": "desc",
        "search_indices": {index_name},
        "reach": None,
        "user_sub": "user_sub",
        "groups": [],
        "visited": [],
    }
    base_data_path = "core/management/commands/data/evaluation"
    documents = []
    queries = []
    id_to_title = {}

    def add_arguments(self, parser):
        parser.add_argument(
            dest="dataset_name",
            type=str,
            help="Name of the dataset to use for evaluation",
        )
        parser.add_argument(
            "--min_score",
            dest="min_score",
            type=float,
            default=0.0,
            help="hits with a score lower than min_score are ignored",
        )
        parser.add_argument(
            "--keep-index",
            dest="keep_index",
            type=bool,
            default=True,
            help="If True the index is not dropped after evaluation.",
        )
        parser.add_argument(
            "--force-reindex",
            dest="force_reindex",
            type=bool,
            default=False,
            help="If True the index is dropped and recreated from scratch even if it already exists.",
        )

    def handle(self, *args, **options):
        """Launch the search engine evaluation."""

        self.init_evaluation(options["dataset_name"], options["force_reindex"])
        self.stdout.write(
            f"[INFO] Starting evaluation with {len(self.documents)} documents and {len(self.queries)} queries"
        )

        evaluations = [
            self.evaluate_query(query, options["min_score"]) for query in self.queries
        ]

        avg_metrics = self.calculate_average_metrics(evaluations)
        self.stdout.write(
            f"\n{'=' * 60}\n"
            f"[SUMMARY] Average Performance\n"
            f"{'=' * 60}\n"
            f"  Average NDCG: {avg_metrics['avg_ndcg']:.2%}\n"
            f"  Average Precision: {avg_metrics['avg_precision']:.2%}\n"
            f"  Average Recall: {avg_metrics['avg_recall']:.2%}\n"
            f"  Average F1-Score: {avg_metrics['avg_f1_score']:.2%}\n"
        )

        self.close_evaluation(options["keep_index"])
        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Evaluation completed"))

    def init_evaluation(self, dataset_name, force_reindex):
        """Initialize evaluation by preparing index and mapping."""
        self.documents = self.load_documents(dataset_name)
        self.queries = (
            importlib.import_module(
                f"core.management.commands.data.evaluation.{dataset_name}.queries"
            )
        ).queries
        self.overwrite_settings()
        check_hybrid_search_enabled.cache_clear()
        delete_search_pipeline()
        ensure_search_pipeline_exists()
        if (
            not opensearch_client().indices.exists(index=self.index_name)
            or force_reindex
        ):
            prepare_index(self.index_name, bulk_create_documents(self.documents))

    def load_documents(self, dataset_name: str):
        """
        Load a dataset module containing a `documents` list and return:
        """

        documents_dir_path = os.path.join(
            self.base_data_path, dataset_name, "documents"
        )
        documents = []
        for filename in os.listdir(documents_dir_path):
            if not filename.endswith(".txt"):
                raise logger.warning(
                    f"Unexpected file format for document: {filename}. Only .txt files are supported."
                )

            str_document_id, title_with_extension = filename.split("_", 1)
            document_id = int(str_document_id)
            document_title = unicodedata.normalize(
                "NFC", title_with_extension.rsplit(".", -1)[0]
            )

            filepath = os.path.join(documents_dir_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            documents.append(
                {
                    "id": document_id,
                    "title": document_title,
                    "content": content,
                }
            )
            self.id_to_title[document_id] = document_title

        return documents

    def evaluate_query(self, query, min_score=0.0):
        """Evaluate a single query and return metrics."""
        results = search(q=query["q"], **self.search_params)
        expected_titles = [
            self.id_to_title[document_id]
            for document_id in query["expected_document_ids"]
        ]
        retrieved_ordered_titles = [
            result["_source"]["title"]
            for result in results["hits"]["hits"]
            if result["_score"] >= min_score
        ]

        metrics = self.calculate_metrics(expected_titles, retrieved_ordered_titles)

        self.stdout.write(
            f"\n[QUERY EVALUATION]\n"
            f"  q: {query['q']}\n"
            f"  expect: {list(expected_titles)}\n"
            f"  result: {list(retrieved_ordered_titles)}\n"
            f"  NDCG: {metrics['ndcg']:.2%} \n"
            f"  PRECISION: {metrics['precision']:.2%} \n"
            f"  RECALL: {metrics['recall']:.2%} \n"
            f"  F1-SCORE: {metrics['f1_score']:.2%} \n"
        )
        return {
            "q": query["q"],
            "expected_titles": expected_titles,
            "retrieved_titles": retrieved_ordered_titles,
            "metrics": metrics,
        }

    def calculate_metrics(self, expected_titles, retrieved_ordered_titles):
        """Calculate precision, recall, F1-score, DCG and NDCG."""

        dcg = self.calculate_dcg(expected_titles, retrieved_ordered_titles)
        idcg = self.calculate_dcg(expected_titles, expected_titles)
        ndcg = dcg / idcg if idcg > 0 else 0
        nb_true_positives = len(set(expected_titles) & set(retrieved_ordered_titles))
        precision = (
            nb_true_positives / len(retrieved_ordered_titles)
            if retrieved_ordered_titles
            else 0
        )
        recall = nb_true_positives / len(expected_titles) if expected_titles else 0
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        return {
            "ndcg": ndcg,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "true_positives": nb_true_positives,
        }

    def calculate_dcg(self, expected_titles, retrieved_ordered_titles):
        """Calculate Discounted Cumulative Gain."""
        return sum(
            (1 if title in expected_titles else 0) / math.log2(rank + 2)
            for rank, title in enumerate(retrieved_ordered_titles)
        ) / len(expected_titles)

    def calculate_average_metrics(self, evaluations):
        """Calculate average metrics across all queries."""
        if not evaluations:
            return {
                "avg_ndcg": 0,
                "avg_precision": 0,
                "avg_recall": 0,
                "avg_f1_score": 0,
            }

        total_ndcg = sum(r["metrics"]["ndcg"] for r in evaluations)
        total_precision = sum(r["metrics"]["precision"] for r in evaluations)
        total_recall = sum(r["metrics"]["recall"] for r in evaluations)
        total_f1 = sum(r["metrics"]["f1_score"] for r in evaluations)
        nb_evaluations = len(evaluations)

        return {
            "avg_ndcg": total_ndcg / nb_evaluations,
            "avg_precision": total_precision / nb_evaluations,
            "avg_recall": total_recall / nb_evaluations,
            "avg_f1_score": total_f1 / nb_evaluations,
        }

    def close_evaluation(self, keep_index):
        """Delete the evaluation index."""
        delete_search_pipeline()
        if not keep_index:
            self.opensearch_client_.indices.delete(index=self.index_name)

    @staticmethod
    def overwrite_settings():
        """Overwrite settings for evaluation purposes."""
        settings.HYBRID_SEARCH_ENABLED = True
        settings.HYBRID_SEARCH_WEIGHTS = [0.2, 0.8]
        settings.EMBEDDING_API_PATH = "https://albert.api.etalab.gouv.fr/v1/embeddings"
        settings.EMBEDDING_REQUEST_TIMEOUT = 10
        settings.EMBEDDING_API_MODEL_NAME = "embeddings-small"
        settings.EMBEDDING_DIMENSION = 1024
