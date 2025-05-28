import re
from ...utils.spread_json_db import SpreadJson
from typing import Dict
from ...globals.g_paths import get_dir
from ...utils.spread_json_db.myhash import hashs
SEP = ", "


DB = SpreadJson.open(get_dir("sdxl", "tag_abbr"), split_method=lambda x: hashs(x, length=2))

def get_db(uid, abbr):
    if (uid not in DB):
        return None
    if (abbr not in DB[uid]):
        return None
    return DB[uid][abbr]

def update_db(uid, abbr, detail):
    user_abbrs = DB.get(uid, {})
    user_abbrs[abbr] = detail
    DB[uid] = user_abbrs


def _split(tagstr):
    return [i.strip() for i in tagstr.split(SEP.strip())]
def _join(tags):
    return SEP.join(i.strip() for i in tags if i.strip())

def _format_comma(tagstr):
    _CN_COMMA = "，"
    tagstr = tagstr.replace(_CN_COMMA, ",")
    return _join(_split(tagstr))

def _pos_neg(prompt):
    pro = []
    neg = []
    p0n1 = False
    PTTN =r"(/\*|\*/)"
    remain = re.split(PTTN, prompt)
    for i in remain:
        if (re.match(PTTN, i)):
            continue
        if (p0n1):
            neg.append(i)
        else:
            pro.append(i)
        p0n1 = not p0n1
    return _format_comma(_join(pro)), _format_comma(_join(neg))

class ProcessPromptAbbrs:
    def __init__(self, prompt: str, abbrs: Dict[str, str]):
        self.input = prompt
        found = []
        
        visited = set()
        while (True):
            prompt = _format_comma(prompt)
            visited.add(prompt)
            keys = sorted(abbrs, key=lambda x: len(x), reverse=True)
            for abbr in keys:
                if (abbr in prompt):
                    found.extend([abbr]*prompt.count(abbr))
                    prompt = prompt.replace(abbr, abbrs[abbr]+SEP)
            prompt = _format_comma(prompt)
            if (prompt in visited):
                # unchanged or loop found
                break
            # else allow chained replacement
        self.result = prompt
        self.found = _format_comma(_join(found))
        

def process_prompt(uid, prompt):
    all_abbrs = [v for k, v in DB.items()]
    user_abbr = DB.get(uid, {})
    abbrs = {}
    for i in all_abbrs:
        abbrs.update(i)
    abbrs.update(user_abbr)

    return ProcessPromptAbbrs(prompt, abbrs)