import datetime
import urllib

import puz
import requests

from .basedownloader import BaseDownloader
from ..util import *

class NewYorkTimesDownloader(BaseDownloader):
    command = 'nyt'
    outlet = 'New York Times'
    outlet_prefix = 'NY Times'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.url_from_id = 'https://www.nytimes.com/svc/crosswords/v2/puzzle/{}.json'
        self.date = None

        self.headers = {}
        self.cookies = {}

        username = self.settings.get('username')
        password = self.settings.get('password')

        if username and password:
            nyts_token = self.authenticate(username, password)
            update_config_file('nyt', {'NYT-S': nyts_token})
        else:
            nyts_token = self.settings.get('NYT-S')

        if not nyts_token:
            raise XWordDLException('No credentials provided or stored. Try running xword-dl nyt --authenticate')
        else:
            self.cookies.update({'NYT-S': nyts_token})

    def authenticate(self, username, password):
        """Given a NYT username and password, returns the NYT-S cookie value"""

        res = requests.post('https://myaccount.nytimes.com/svc/ios/v2/login',
                data={'login': username, 'password': password},
                headers={'User-Agent':
                    'Crossword/1844.220922 CFNetwork/1335.0.3 Darwin/21.6.0',
                    'client_id': 'ios.crosswords',})

        res.raise_for_status()

        nyts_token = ''

        for cookie in res.json()['data']['cookies']:
            if cookie['name'] == 'NYT-S':
                nyts_token = cookie['cipheredValue']

        if nyts_token:
            return nyts_token
        else:
            raise XWordDLException('NYT-S cookie not found.')

    def parse_date_from_url(self, url):
        path = urllib.parse.urlparse(url).path
        date_string = ''.join(path.split('/')[-3:])

        return datetime.datetime.strptime(date_string, '%Y%m%d')

    def find_latest(self):
        oracle = "https://www.nytimes.com/svc/crosswords/v2/oracle/daily.json"

        res = requests.get(oracle)
        puzzle_id = res.json()['results']['current']['puzzle_id']

        url = self.url_from_id.format(puzzle_id)

        return url

    def find_by_date(self, dt):
        lookup_url = 'https://www.nytimes.com/svc/crosswords/v3/puzzles.json?status=published&order=published&sort=asc&pad=false&print_date_start={}&print_date_end={}&publish_type=daily'

        formatted_date = dt.strftime('%Y-%m-%d')

        res = requests.get(lookup_url.format(formatted_date, formatted_date))

        puzzle_id = res.json()['results'][0]['puzzle_id']

        return self.url_from_id.format(puzzle_id)

    def find_solver(self, url):
        return url

    def fetch_data(self, solver_url):
        res = requests.get(solver_url, cookies=self.cookies)
        res.raise_for_status()

        return res.json()['results'][0]

    def parse_xword(self, xword_data):
        puzzle = puz.Puzzle()

        metadata = xword_data.get('puzzle_meta')
        puzzle.author = metadata.get('author').strip()
        puzzle.copyright = metadata.get('copyright').strip()
        puzzle.height = metadata.get('height')
        puzzle.width = metadata.get('width')

        if metadata.get('notes'):
            puzzle.notes = metadata.get('notes')[0]['txt'].strip()

        date_string = metadata.get('printDate')

        if not self.date:
            self.date = datetime.datetime.strptime(date_string, '%Y-%m-%d')

        puzzle.title = metadata.get('title') or self.date.strftime(
                '%A, %B %d, %Y')

        try:
            puzzle_data = xword_data['puzzle_data']
        except:
            raise XWordDLException('Puzzle data not available. Try re-authenticating with xword-dl nyt --authenticate')

        solution = ''
        fill = ''
        markup = b''
        rebus_board = []
        rebus_index = 0
        rebus_table = ''

        for idx, square in enumerate(puzzle_data['answers']):
            if not square:
                solution += '.'
                fill += '.'
                rebus_board.append(0)
            elif len(square) == 1:
                solution += square
                fill += '-'
                rebus_board.append(0)
            else:
                solution += square[0][0]
                fill += '-'
                rebus_board.append(rebus_index + 1)
                rebus_table += '{:2d}:{};'.format(rebus_index, square[0])
                rebus_index += 1

            markup += (b'\x80' if puzzle_data['layout'][idx] == 3 else b'\x00')

        puzzle.solution = solution
        puzzle.fill = fill

        clue_list = puzzle_data['clues']['A'] + puzzle_data['clues']['D']
        clue_list.sort(key=lambda c: c['clueNum'])

        puzzle.clues = [unidecode(c['value']).strip() for c in clue_list]

        if b'\x80' in markup:
            puzzle.extensions[b'GEXT'] = markup
            puzzle._extensions_order.append(b'GEXT')
            puzzle.markup()

        if any(rebus_board):
            puzzle.extensions[b'GRBS'] = bytes(rebus_board)
            puzzle.extensions[b'RTBL'] = rebus_table.encode(puz.ENCODING)
            puzzle._extensions_order.extend([b'GRBS', b'RTBL'])
            puzzle.rebus()

        return puzzle

    def pick_filename(self, puzzle, **kwargs):
        if puzzle.title == self.date.strftime('%A, %B %d, %Y'):
            title = ''
        else:
            title = puzzle.title

        return super().pick_filename(puzzle, title=title, **kwargs)


class NewYorkTimesVarietyDownloader(NewYorkTimesDownloader):
    command = 'nytv'
    outlet = 'New York Times Variety'
    prefix = 'NY Times Variety'

    def __init__(self, **kwargs):
        self.command = 'nyt' # sort of a hack to use the stored settings
                             # for nyt, doesn't actually affect command
        super().__init__(**kwargs)
        self.command = 'nytv' # but we change it back anyway

        self.url_from_id = 'https://www.nytimes.com/svc/crosswords/v6/puzzle/variety/{}.json'

    def find_latest(self):
        raise XWordDLException('Search by latest not supported for NYT Variety puzzles. Try searching by date or passing a URL.')

    def find_by_date(self, dt):
        formatted_date = dt.strftime('%Y-%m-%d')

        return self.url_from_id.format(formatted_date)

    def fetch_data(self, solver_url):
        try:
            res = requests.get(solver_url, cookies=self.cookies)
            res.raise_for_status()
        except requests.exceptions.HTTPError:
            raise XWordDLException('No puzzle found for that date.')

        return res.json()

    def parse_xword(self, xword_data):
        puzzle = puz.Puzzle()

        puzzle.author = xword_data['constructors'][0].strip()
        puzzle.copyright = xword_data['copyright'].strip()
        puzzle.height = int(xword_data['body'][0]['dimensions']['height'])
        puzzle.width =  int(xword_data['body'][0]['dimensions']['width'])

        puzzle.title = xword_data['title']

        if not self.date:
            self.date = datetime.strptime(xword_data['publicationDate'],
                                          '%Y-%m-%d')
        solution = ''
        fill = ''

        for idx, square in enumerate(xword_data['body'][0]['cells']):
            if not square:
                solution += '.'
                fill += '.'
            else:
                solution += square['answer']
                fill += '-'

        puzzle.solution = solution
        puzzle.fill = fill

        clue_list = xword_data['body'][0]['clues']
        clue_list.sort(key=lambda c: (int(c['label']), c['direction']))

        puzzle.clues = [c['text'][0]['plain'] for c in clue_list]

        return puzzle
