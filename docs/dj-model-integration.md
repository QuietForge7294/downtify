# Tests d’intégration des modèles DJ

Les deux tests existants de `tests/music_ai/test_dj_worker.py` peuvent utiliser un répertoire de poids vérifiés avec `DOWNTIFY_TEST_DJ_MODELS`. Sans ce réglage, ils gardent leur emplacement `/models` habituel et leurs critères de sélection précédents. Aucune assertion n’est retirée.

Exemple de reproduction sur Linux, dans l’environnement CPU de la recette DJ :

```sh
DOWNTIFY_TEST_DJ_MODELS=/chemin/poids-verifies HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 taskset -c CPU_DISPONIBLE python -m pytest tests/music_ai/test_dj_worker.py -q -rA
```

Les poids `small0` et `final0` viennent de l’adresse publique publiée dans le paquet officiel BeatThis 1.1.0. Leurs SHA-256 sont comparés aux constantes `PINS` avant le chargement ; aucun fichier musical de bibliothèque n’est téléchargé ni utilisé dans ces essais. Le moteur reste chargé entre les requêtes et la seconde session sur les mêmes sources réutilise les profils sans nouveau processus d’analyse. Désactiver la préparation empêche la publication d’un set. Les empreintes des fichiers originaux synthétiques sont vérifiées.

Résultat local : deux tests passent, aucun exclu. Un seul CPU logique est autorisé. Le pic échantillonné de RSS cumulée du processus de test et de ses descendants est de 593842176 octets, environ 566 Mio, sur 7,561 secondes d’exécution surveillée. Le watchdog arrête ce groupe de test au-delà de 2 Gio ou dix minutes. La somme RSS peut compter plusieurs fois des pages partagées et n’est pas une mesure de pic mémoire de conteneur. Voir [la preuve structurée](dj-model-integration-proof.json) pour les versions, empreintes et limites.

Ces résultats utilisent des sons synthétiques courts et le FFmpeg local. Ils ne mesurent pas le premier son sur téléphone, un P95 sur trente démarrages, vingt transitions musicales multigenres ou une heure de direct. La qualification de la bibliothèque et du matériel reste séparée. Les deux tests restent optionnels dans une exécution qui ne fournit pas les modèles ; leur absence n’est pas présentée comme un essai réussi.

Les versions PyTorch et TorchAudio restent celles de la recette. [La documentation officielle TorchAudio](https://docs.pytorch.org/audio/stable/installation.html) décrit la compatibilité ABI stable de TorchAudio 2.11 avec PyTorch 2.11 et les versions suivantes.
