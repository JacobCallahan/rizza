from difflib import SequenceMatcher


def similarity(term1, term2):
    return SequenceMatcher(None, term1, term2).ratio()


def fuzzyfind(needle, haystack, threshold=0.9):
    if needle in haystack:
        return 1
    else:
        split_needle = needle.split()
        split_stack = haystack.split()
        total, needle_len = (0.0, len(split_needle))
        curr_needle = split_needle.pop(0)
        for i in split_stack:
            if similarity(curr_needle, i) >= threshold:
                total += similarity(curr_needle, i)
                if split_needle:
                    curr_needle = split_needle.pop(0)
        return total / needle_len


def pmatch(needle, haystack, threshold=0.9):
    if needle in haystack:
        return (1, haystack.index(needle))
    else:
        needle_len = len(needle.split())
        split_stack = haystack.split()
        best_match = (0, 0)
        for i in range(len(split_stack)):
            if i + needle_len <= len(split_stack):
                presult = similarity(needle, " ".join(split_stack[i: i + needle_len]))
                if presult >= best_match[0]:
                    best_match = (presult, i)
        return best_match
