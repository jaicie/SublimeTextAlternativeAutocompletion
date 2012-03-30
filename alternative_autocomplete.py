import sublime
import sublime_plugin
import re
import os.path
from levenshtein import levenshtein


def uniq(list):
    seen = set()
    return [value for value in list if value not in seen and not seen.add(value)]


def fuzzy_match(prefix, word):
    prefix, word = prefix.lower(), word.lower()
    query_i, word_i, next_i = 0, -1, -1
    while query_i < len(prefix):
        word_i = word.find(prefix[query_i], word_i + 1)
        if word_i <= next_i:
            return False
        query_i += 1
        next_i = word_i
    return True


class Candidate:
    def __init__(self, distance, text):
        self.distance = distance
        self.text = text

    def __hash__(self):
        return hash(self.text)

    def __cmp__(self, other):
        return cmp(self.text, other.text)


class AlternativeAutocompleteCommand(sublime_plugin.TextCommand):

    candidates = []
    previous_completion = None

    def run(self, edit, cycle='next', default=''):
        self.edit = edit
        text = self.view.substr(sublime.Region(0, self.view.size()))
        # lines = self.view.substr(sublime.Region(0, self.view.size())).splitlines()
        # remove initial indentation.  this makes the "distance" calculation more equitable
        # text = "\n".join(map(lambda s: re.sub('^[ \t]+', '', s), lines))
        self.insert_completion(self.view.sel()[0].b, text, cycle, default)

    def insert_completion(self, position, text, cycle, default):
        prefix_match = re.search(r'([\w\d_]+)\Z', text[0:position], re.M | re.U)
        if prefix_match:
            current_word_match = re.search(r'^([\w\d_]+)', text[prefix_match.start(1):], re.M | re.U)
            if current_word_match:
                current_word = current_word_match.group(1)
            else:
                current_word = None

            prefix = prefix_match.group(1)
            if self.previous_completion is None or prefix != self.previous_completion:
                self.previous_completion = None
                self.candidates = self.find_candidates(prefix, position, text)
                if current_word in self.candidates:
                    self.candidates.remove(current_word)
            if self.candidates:
                edit = self.view.begin_edit()
                self.view.erase(edit, sublime.Region(prefix_match.start(1), prefix_match.end(1)))
                if self.previous_completion is None:
                    completion = self.candidates[0]
                else:
                    if cycle == 'previous':
                        direction = -1
                    else:
                        direction = 1
                    completion = self.candidates[(self.candidates.index(self.previous_completion) + direction) % len(self.candidates)]
                self.view.insert(edit, prefix_match.start(1), completion)
                self.view.end_edit(edit)
                self.previous_completion = completion
        else:
            if default and default != '':
                self.view.insert(self.edit, position, default)

    def find_candidates(self, prefix, position, text):
        candidates = self.populate_candidates(prefix)

        regex = re.compile(r'[^\w\d](' + re.escape(prefix) + r'[\w\d]+)', re.M | re.U)
        for match in regex.finditer(text):
            candidates.append(Candidate(abs(match.start(1) - position), match.group(1)))

        if candidates:
            candidates.sort(lambda a, b: cmp(a.distance, b.distance))
            candidates = [candidate.text for candidate in candidates]
            if len(candidates) > 100:
                candidates = candidates[0:99]
        else:
            word_regex = re.compile(r'\b' + re.escape(prefix[0:1]) + r'[\w\d]+', re.M | re.U | re.I)
            words = word_regex.findall(text)
            candidates = [word for word in words if word != prefix and fuzzy_match(prefix, word)]
            candidates.sort(lambda a, b: cmp(levenshtein(prefix, a), levenshtein(prefix, b)))
        if candidates:
            candidates.append(prefix)
        return uniq(candidates)

    def populate_candidates(self, prefix):
        settings_name, _ = os.path.splitext(os.path.basename(self.view.settings().get('syntax')))
        default_settings = sublime.load_settings("alternative_autocompletion.sublime-settings")
        default_candidates = default_settings.get(settings_name)

        user_settings = sublime.load_settings(settings_name + ".sublime-settings")
        user_candidates = user_settings.get('autocomplete')

        # some languages, like "HTML 5", map to another language, like "PHP"
        # so if default_candidates is a str/unicode, look for that list
        while isinstance(default_candidates, basestring):
            settings_name = default_candidates
            default_candidates = default_settings.get(settings_name)
            if not user_candidates:
                user_settings = sublime.load_settings(settings_name + ".sublime-settings")
                user_candidates = user_settings.get('autocomplete')

        if default_candidates:
            candidates = [Candidate(self.view.size(), c) for c in default_candidates if c[:len(prefix)] == prefix]
        else:
            candidates = []

        # now merge user settings
        if user_candidates:
            candidates.extend([Candidate(self.view.size(), c) for c in user_candidates if c[:len(prefix)] == prefix])

        return candidates
