import requests
import re

# for hinshi, kanou and hosetsu see page of 行く（ゆく）
# for hinshi, hasei see 剛直
GRAMMATICAL_CLASSES = "hinshi|hasei|kanou|hosetsu"
# dictionary entry object to organize the word and definitions.
class dictionaryEntry:

    @classmethod
    def fromSearchPage(cls, name, dataHTML):
        shortDef = re.search(r'<p class="text">(.+?)</p>',dataHTML).group(1)
        url = "https://dictionary.goo.ne.jp"+re.search(r'(/word/.+?)"',dataHTML).group(1)
        word = re.search(r'<p class="title">(.+?) ', dataHTML).group(1)
        if "【" in word:
            word_kanji = re.search(r'【(.+?)】', word).group(1)
            word_reading = re.sub(r'【.+?】', "", word)
            word_reading = word_reading.replace("‐","")
            word = f"{word_kanji}（{word_reading}）"
        return cls(name, word, shortDef, url)

    @classmethod
    def fromEntryPage(cls, name, dataHTML):
        word = re.search(r'"og:title" content="(.+?)の意味',dataHTML,re.DOTALL).group(1)
        reg = re.compile('<div id="jn-.+?_".+?<div class="content-box contents_area meaning_area p10">(.+?)<!-- /contents -->',re.DOTALL)
        shortDef = cleanDefinition(re.search(reg,dataHTML).group(1))
        return cls(name, word, shortDef, "")

    def __init__(self, name, word, shortDef, url):
        self.name = name
        self.shortDef = re.sub(r'<img.+?>|&#x32..;',"",shortDef)
        self.url = url
        self.word = word
    
    @classmethod
    def failedSearchEntry(cls, word):
        return cls("失敗","失敗","goo辞書で「" + word + "」に一致する情報は見つかりませんでした","")

    @classmethod
    def connectionErrorEntry(cls):
        return cls("失敗","失敗","goo辞書に接続出来ませんでした","")

    # returns an expanded version of the definition
    def getFullDef(self):
        if self.url == "" or self.shortDef[-3:] != "...":
            return self.shortDef
        else:
            try:
                idNum = self.url.split('#')[-1]
                entryPage = requests.get(self.url).text
                reg = re.compile('<div id="' + idNum + '_".+?<div class="content-box contents_area meaning_area p10">(.+?)<!-- /contents -->',re.DOTALL)
                return cleanDefinition(re.search(reg,entryPage).group(1))
            except requests.exceptions.ConnectionError:
                return self.shortDef

    def __str__(self):
        return self.word+ ": " + self.shortDef

def _clean_interior_definition(input_html: str) -> str:
    """
    Clean the html strings for each grammatical role.
    """

    # on some pages html tags are separated by newlines for some reason (see
    # 公平無私 page)
    input_html = input_html.replace("\n","")

    # if there is not a list of definitions the div class is text
    no_list = '<div class="text">.+?</div>'

    # if there are multiple definitions, goo opens an unordered list for every list item
    list_item_open = '<ol class="meaning cx"><li><!-- l-ol-->'
    list_item_close = '</li></ol><!-- /l-ol -->'

    # quotes are contained as nested list and marked with the m-ol instead of
    # l-ol.
    nested_list_open = '<ol class="meaning cx"><li><!-- m-ol-->'
    nested_list_close = '</ol><!-- /m-ol -->'

    # the actual content of the list items actually beings at the <p
    # class="text">
    list_item = '<p class="text">.+?</p>'

    dirty_lines = re.findall(r'|'.join([no_list, list_item_open, list_item_close,
                                        nested_list_open, nested_list_close,
                                        list_item]), input_html, re.DOTALL)

    answer = ""
    in_list = False
    for line in dirty_lines:
        if line == list_item_open:
            if not in_list:
                answer += "<ol><li>"
                in_list = True
                continue
            else:
                answer += "<li>"
                continue

        if line == list_item_close:
            answer += "</li>\n"
            continue

        if line in [nested_list_open, nested_list_close]:
            continue

        # instead of using HTML lists to number, goo used hardcoded numbers
        # with fullwidth numbers for single digit entries and half-width for
        # higher numbers
        answer += re.sub(r'<strong>(?:１|２|３|４|５|６|７|８|９|[0-9][0-9]+)'
                          '</strong>|<.*?>|&thinsp;|&#x32..;', "", line)

        if not in_list:
            answer += "\n"

    if in_list:
        answer += "</ol>\n"
    return answer

def cleanDefinition(dirty):
    # the overarching 'sections' of a dictionary entry are introduced by <span
    # class="{GRAMMATICAL_CLASSES}">[...]</span> blocks, if there is more than
    # one role we want this to be an unordered list.
    grammar_search = fr'\n(?=[^\n]+<span class="(?:{GRAMMATICAL_CLASSES})">(?:［|\[).+?(?:］|\])</span>[^\n]+)'
    span_splits = re.split(grammar_search, dirty)

    answer = ""
    
    # first split is the one before the first with a span so skip
    if len(span_splits) > 2:
        answer += "<ol>\n"
        for split in span_splits[1:]:
            answer += "<li>"
            answer += _clean_interior_definition(split)
            answer += "</li>\n"
        answer += "</ol>"
    else:
        answer = _clean_interior_definition(span_splits[-1])

    return answer


# Returns the encoding of the word as used in goo辞書's url
def urlEncode(word):
    codedWord = str(word.encode('utf-8'))[2:-1].upper()
    finalized = ""
    for i in range(2, len(codedWord)-1 ,4):
        finalized = finalized + "%" + codedWord[i:i+2]
    return "https://dictionary.goo.ne.jp/srch/jn/" + finalized + "/m1u/"

# searches for the passed word, returning the html of the page
def getSearchPage(word):
    print(urlEncode(word))
    searchPage = requests.get(urlEncode(word)).text
    if "一致する情報は見つかりませんでした" in searchPage:
        raise ValueError("goo辞書で一致する情報は見つかりませんでした")
    return searchPage

# Returns an array containing dictionaryEntry objects corresponding to the word passed as a parameter
def parseSearch(word):
    try:
        searchPage = getSearchPage(word)
    except ValueError:
        return [dictionaryEntry.failedSearchEntry(word)]
    except requests.exceptions.ConnectionError:
        return [dictionaryEntry.connectionErrorEntry()]

    try:
        resultsString = re.search(r'<ul class="content_list idiom lsize">(.+?)</div>', searchPage, re.DOTALL).group(1)
    except AttributeError:
        return [dictionaryEntry.fromEntryPage(word, searchPage)]

    entries = []
    for result in re.findall(r'<a href=.+?</a>', resultsString,re.DOTALL):
        entries.append(dictionaryEntry.fromSearchPage(word, result))
    return entries

def test(word):
    for entry in parseSearch(word):
        print(entry.word + entry.getFullDef())

# test("行く")
# test("現状")
# test("公平無私")
# test("剛直")
