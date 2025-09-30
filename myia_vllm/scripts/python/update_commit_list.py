import json
import os
from datetime import datetime

def parse_date(date_str):
    if not date_str:
        return datetime.min
    # Essayer le format ISO 8601
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        # Essayer l'autre format
        try:
            return datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        except (ValueError, TypeError):
            print(f"Warning: Could not parse date '{date_str}'.")
            return datetime.min

def update_commit_list(file_path):
    # Les nouveaux commits
    new_commits = [
      {
        "sha": "34529217d32a71714d421d09fc95dcc9bb066fe77",
        "author": "Stefan Schwarz",
        "date": "2024-02-16T20:27:14+01:00",
        "subject": "Add docker-compose.yml and corresponding .env"
      },
      {
        "sha": "9a4b60a4c91d972116c01e818048ab8868542d62",
        "author": "Wolfram Ravenwolf",
        "date": "2024-11-24T13:48:07+01:00",
        "subject": "Merge branch 'vllm-project:main' into docker-compose"
      },
      {
        "sha": "bc4e364e83c6c429e04fce3fab0daee6c3f24806c",
        "author": "Wolfram Ravenwolf",
        "date": "2024-11-24T18:40:21+01:00",
        "subject": "Adjust docker-compose.yml and corresponding .env"
      },
      {
        "sha": "93fe97e4b268f5483940eee0a8ee9aa314320164e",
        "author": "Roo",
        "date": "2025-08-04T23:06:47+02:00",
        "subject": "Sauvegarde de l'état dégradé avant restauration"
      }
    ]
    
    # Lire le fichier existant
    commit_list = []
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                content = f.read()
                if content.strip():
                    commit_list = json.loads(content)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from {file_path}. Treating as empty.")
                commit_list = []

    # Combiner et filtrer les entrées invalides
    combined_list = [c for c in (commit_list + new_commits) if c]

    # Trier la liste
    sorted_list = sorted(combined_list, key=lambda x: parse_date(x.get('date')))

    # Ré-indexer
    for i, commit in enumerate(sorted_list):
        commit['index'] = i
        if 'author' not in commit:
            commit['author'] = 'Unknown'

    # Ecrire le résultat
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_list, f, indent=4, ensure_ascii=False)

    print(f"Successfully updated {file_path} with {len(sorted_list)} commits.")

if __name__ == "__main__":
    # Ajuster le chemin relatif pour l'exécution depuis la racine
    target_file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'archeology', 'MASTER_COMMIT_LIST_JSBOIGE.json')
    update_commit_list(os.path.normpath(target_file_path))