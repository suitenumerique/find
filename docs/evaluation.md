This file keeps for reference the logs of the last best evaluation of the model.

````
(venv) ➜  find git:(evaluate) ✗ docker compose exec app python manage.py evaluate_search_engine v1 --min_score 0.5   

2025-11-20 18:44:30,903 core.services.opensearch INFO Hybrid search is disabled via HYBRID_SEARCH_ENABLED setting
2025-11-20 18:44:31,183 core.management.commands.utils INFO Deleting search pipeline hybrid-search-pipeline
2025-11-20 18:44:31,201 opensearch INFO DELETE http://opensearch:9200/_search/pipeline/hybrid-search-pipeline [status:200 request:0.018s]
2025-11-20 18:44:31,202 opensearch WARNING GET http://opensearch:9200/_search/pipeline/hybrid-search-pipeline [status:404 request:0.001s]
2025-11-20 18:44:31,202 core.management.commands.create_search_pipeline INFO Creating search pipeline: hybrid-search-pipeline
2025-11-20 18:44:31,221 opensearch INFO PUT http://opensearch:9200/_search/pipeline/hybrid-search-pipeline [status:200 request:0.019s]
2025-11-20 18:44:31,222 opensearch INFO HEAD http://opensearch:9200/evaluation-index [status:200 request:0.001s]
[INFO] Starting evaluation with 76 documents and 12 queries
2025-11-20 18:44:31,222 core.services.opensearch INFO embed: 'cours d'histoire de l'antiquité'
2025-11-20 18:44:31,302 core.services.opensearch INFO Performing hybrid search with embedding: cours d'histoire de l'antiquité
2025-11-20 18:44:31,317 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.014s]

[QUERY EVALUATION]
  q: cours d'histoire de l'antiquité
  expect: ["L'Empire Romain", "L'Égypte Ancienne"]
  result: ["L'Égypte Ancienne", 'La Sculpture sur Pierre']
  NDCG: 61.31% 
  PRECISION: 50.00% 
  RECALL: 50.00% 
  F1-SCORE: 50.00% 
2025-11-20 18:44:31,317 core.services.opensearch INFO embed: 'recette salée végétarienne'
2025-11-20 18:44:31,392 core.services.opensearch INFO Performing hybrid search with embedding: recette salée végétarienne
2025-11-20 18:44:31,403 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.010s]

[QUERY EVALUATION]
  q: recette salée végétarienne
  expect: ['Ratatouille Provençale', 'Salade de légumes', 'Fondue Savoyarde']
  result: ['Salade de légumes']
  NDCG: 46.93% 
  PRECISION: 100.00% 
  RECALL: 33.33% 
  F1-SCORE: 50.00% 
2025-11-20 18:44:31,403 core.services.opensearch INFO embed: 'art dramatique'
2025-11-20 18:44:31,475 core.services.opensearch INFO Performing hybrid search with embedding: art dramatique
2025-11-20 18:44:31,486 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.011s]

[QUERY EVALUATION]
  q: art dramatique
  expect: ['Le Théâtre']
  result: ['Le Théâtre', 'Le Vitrail']
  NDCG: 100.00% 
  PRECISION: 50.00% 
  RECALL: 100.00% 
  F1-SCORE: 66.67% 
2025-11-20 18:44:31,487 core.services.opensearch INFO embed: 'art de bouger son corps'
2025-11-20 18:44:31,556 core.services.opensearch INFO Performing hybrid search with embedding: art de bouger son corps
2025-11-20 18:44:31,573 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.017s]

[QUERY EVALUATION]
  q: art de bouger son corps
  expect: ['La Danse', 'La Danse Contemporaine']
  result: ['La Danse', 'La Danse Contemporaine']
  NDCG: 100.00% 
  PRECISION: 100.00% 
  RECALL: 100.00% 
  F1-SCORE: 100.00% 
2025-11-20 18:44:31,573 core.services.opensearch INFO embed: 'mammifères aquatiques'
2025-11-20 18:44:31,641 core.services.opensearch INFO Performing hybrid search with embedding: mammifères aquatiques
2025-11-20 18:44:31,654 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.013s]

[QUERY EVALUATION]
  q: mammifères aquatiques
  expect: ['Le Dauphin', 'La Baleine à Bosse']
  result: ['Le Dauphin', 'La Baleine à Bosse', 'Le Manchot Empereur', 'Le Requin Blanc', 'Le Paresseux']
  NDCG: 100.00% 
  PRECISION: 40.00% 
  RECALL: 100.00% 
  F1-SCORE: 57.14% 
2025-11-20 18:44:31,654 core.services.opensearch INFO embed: 'insectes pollinisateurs'
2025-11-20 18:44:31,733 core.services.opensearch INFO Performing hybrid search with embedding: insectes pollinisateurs
2025-11-20 18:44:31,746 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.012s]

[QUERY EVALUATION]
  q: insectes pollinisateurs
  expect: ["L'Abeille"]
  result: ["L'Abeille", 'Le Caméléon', 'Le Papillon Monarque']
  NDCG: 100.00% 
  PRECISION: 33.33% 
  RECALL: 100.00% 
  F1-SCORE: 50.00% 
2025-11-20 18:44:31,746 core.services.opensearch INFO embed: 'prédateur félin'
2025-11-20 18:44:31,820 core.services.opensearch INFO Performing hybrid search with embedding: prédateur félin
2025-11-20 18:44:31,834 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.014s]

[QUERY EVALUATION]
  q: prédateur félin
  expect: ["Le Lion d'Afrique", 'Le Guépard']
  result: ["Le Lion d'Afrique", 'Le Guépard', 'Le Requin Blanc', "L'éléphant", 'Le Hibou Grand-Duc', "L'Ours polaire", 'Le Serpent Python']
  NDCG: 100.00% 
  PRECISION: 28.57% 
  RECALL: 100.00% 
  F1-SCORE: 44.44% 
2025-11-20 18:44:31,835 core.services.opensearch INFO embed: 'elephant'
2025-11-20 18:44:31,906 core.services.opensearch INFO Performing hybrid search with embedding: elephant
2025-11-20 18:44:31,920 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.013s]

[QUERY EVALUATION]
  q: elephant
  expect: ["L'Éléphant d'Asie", "L'éléphant"]
  result: ["L'éléphant", "L'Éléphant d'Asie"]
  NDCG: 100.00% 
  PRECISION: 100.00% 
  RECALL: 100.00% 
  F1-SCORE: 100.00% 
2025-11-20 18:44:31,920 core.services.opensearch INFO embed: 'courir'
2025-11-20 18:44:31,994 core.services.opensearch INFO Performing hybrid search with embedding: courir
2025-11-20 18:44:32,010 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.015s]

[QUERY EVALUATION]
  q: courir
  expect: ['Il va courir']
  result: ['Il va courir']
  NDCG: 100.00% 
  PRECISION: 100.00% 
  RECALL: 100.00% 
  F1-SCORE: 100.00% 
2025-11-20 18:44:32,011 core.services.opensearch INFO embed: 'football'
2025-11-20 18:44:32,082 core.services.opensearch INFO Performing hybrid search with embedding: football
2025-11-20 18:44:32,089 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.007s]

[QUERY EVALUATION]
  q: football
  expect: ['Foot']
  result: ['Foot']
  NDCG: 100.00% 
  PRECISION: 100.00% 
  RECALL: 100.00% 
  F1-SCORE: 100.00% 
2025-11-20 18:44:32,089 core.services.opensearch INFO embed: 'couri'
2025-11-20 18:44:32,156 core.services.opensearch INFO Performing hybrid search with embedding: couri
2025-11-20 18:44:32,163 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.007s]

[QUERY EVALUATION]
  q: couri
  expect: ['Il va courir']
  result: ['Coq au Vin', 'Il va courir', 'Clafoutis aux Cerises']
  NDCG: 63.09% 
  PRECISION: 33.33% 
  RECALL: 100.00% 
  F1-SCORE: 50.00% 
2025-11-20 18:44:32,164 core.services.opensearch INFO embed: 'courrir'
2025-11-20 18:44:32,231 core.services.opensearch INFO Performing hybrid search with embedding: courrir
2025-11-20 18:44:32,240 opensearch INFO POST http://opensearch:9200/evaluation-index/_search?search_pipeline=hybrid-search-pipeline&ignore_unavailable=true [status:200 request:0.009s]

[QUERY EVALUATION]
  q: courrir
  expect: ['Il va courir']
  result: ['Il va courir']
  NDCG: 100.00% 
  PRECISION: 100.00% 
  RECALL: 100.00% 
  F1-SCORE: 100.00% 

============================================================
[SUMMARY] Average Performance
============================================================
  Average NDCG: 89.28%
  Average Precision: 69.60%
  Average Recall: 90.28%
  Average F1-Score: 72.35%
2025-11-20 18:44:32,241 core.management.commands.utils INFO Deleting search pipeline hybrid-search-pipeline
2025-11-20 18:44:32,258 opensearch INFO DELETE http://opensearch:9200/_search/pipeline/hybrid-search-pipeline [status:200 request:0.017s]

[SUCCESS] Evaluation completed
````
