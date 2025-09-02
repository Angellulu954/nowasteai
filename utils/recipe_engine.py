import json
import os
import re
from collections import Counter

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'recipes.json')

def load_recipes():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_token(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9\s]', '', s)
    return re.sub(r'\s+', ' ', s)

def normalize_ingredient_list(ingredients_text_or_list):
    if isinstance(ingredients_text_or_list, (list, set, tuple)):
        tokens = [normalize_token(x) for x in ingredients_text_or_list]
    else:
        tokens = [normalize_token(x) for x in re.split(r'[\n,;]+', ingredients_text_or_list) if x.strip()]
    # collapse plurals / simple stems
    normalized = []
    for t in tokens:
        if t.endswith('es'):
            t = t[:-2]
        elif t.endswith('s'):
            t = t[:-1]
        normalized.append(t)
    return set(filter(None, normalized))

def score_recipe(user_ing: set, recipe: dict):
    recipe_ing = set(normalize_ingredient_list(recipe['ingredients']))
    have = user_ing & recipe_ing
    missing = recipe_ing - user_ing
    coverage = len(have) / max(1, len(recipe_ing))
    # reward fewer missing items and key staples
    staple_boost = len(have & {'onion','garlic','salt','oil','tomato','rice','egg','flour'}) * 0.03
    score = coverage + staple_boost
    return score, sorted(have), sorted(missing)

def suggest_recipes(user_ing: set, top_k: int = 12):
    recipes = load_recipes()
    scored = []
    for r in recipes:
        s, have, miss = score_recipe(user_ing, r)
        result = dict(r)
        result['score'] = round(s, 4)
        result['have'] = have
        result['missing'] = miss
        result['missing_count'] = len(miss)
        scored.append(result)
    scored.sort(key=lambda x: (x['missing_count'], -x['score']))
    return scored[:top_k]
