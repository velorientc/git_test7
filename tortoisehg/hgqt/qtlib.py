# common colors

DRED = '#900000'
DGREEN = '#006400'
DBLUE = '#000090'
DYELLOW = '#6A6A00'
DORANGE = '#AA5000'
DGRAY = '#404040'

PRED = '#ffcccc'
PGREEN = '#aaffaa'
PBLUE = '#aaddff'
PYELLOW = '#ffffaa'
PORANGE = '#ffddaa'

RED = 'red'
GREEN = 'green'
BLUE = 'blue'
YELLOW = 'yellow'
BLACK = 'black'
WHITE = 'white'
GRAY = 'gray'

NORMAL = BLACK
NEW_REV_COLOR = DGREEN
CHANGE_HEADER = GRAY
UP_ARROW_COLOR = '#feaf3e'
DOWN_ARROW_COLOR = '#8ae234'
STAR_COLOR = '#fce94f'
CELL_GRAY = '#2e3436'
STATUS_HEADER = '#DDDDDD'
STATUS_REJECT_BACKGROUND = '#EEEEEE'
STATUS_REJECT_FOREGROUND = '#888888'

LabelStyles = {
    'error':            'font-weight: bold; color: %s;' % DRED,
    'control':          'font-weight: bold; color: %s;' % BLACK,
    'ui.debug':         'font-weight: lighter; color: %s;' % BLACK,
    'ui.status':        'color: %s;' % DGRAY,
    'ui.note':          'color: %s;' % BLACK,
    'ui.warning':       'font-weight: bold; color: %s;' % RED,
    'log.summary':      'color: %s;' % BLACK,
    'log.description':  'color: %s;' % DGRAY,
    'log.changeset':    'color: %s;' % GRAY,
    'log.tag':          'color: %s;' % RED,
    'log.user':         'color: %s;' % BLUE,
    'log.date':         'color: %s;' % BLACK,
    'log.files':        'color: %s;' % BLACK,
    'log.copies':       'font-weight: bold; color: %s;' % BLACK,
    'log.node':         'color: %s;' % BLACK,
    'log.branch':       'color: %s;' % BLACK,
    'log.parent':       'color: %s;' % BLACK,
    'log.manifest':     'color: %s;' % BLACK,
    'log.extra':        'color: %s;' % BLACK,
    'diff.diffline':    'color: %s;' % BLACK,
    'diff.inserted':    'color: %s;' % DGREEN,
    'diff.deleted':     'color: %s;' % RED,
    'diff.hunk':        'color: %s;' % BLUE,
    'diff.file_a':      'font-weight: bold; color: %s;' % BLACK,
    'diff.file_b':      'font-weight: bold; color: %s;' % BLACK,
}

# These labels are unreachable by TortoiseHg consoles, so we leave them
# out for efficiency
unusedLabelStyles = {
    'qseries.applied':  'color: %s;' % BLACK,
    'qseries.unapplied':'color: %s;' % DGRAY,
    'qseries.guarded':  'color: %s;' % BLUE,
    'qseries.missing':  'color: %s;' % DRED,
    'qguard.patch':     'color: %s;' % BLACK,
    'qguard.positive':  'color: %s;' % DGREEN,
    'qguard.negagive':  'color: %s;' % BLUE,
    'qguard.unguarded': 'color: %s;' % DGRAY,
    'diffstat.inserted':'color: %s;' % DGREEN,
    'diffstat.deleted': 'color: %s;' % RED,
    'bookmarks.current':'font-weight: bold; color: %s;' % BLACK,
    'resolve.resolved': 'color: %s;' % DGREEN,
    'resolve.unresolved':'color: %s;' % RED,
    'grep.match':       'font-weight: bold; color: %s;' % BLACK,
    'status.modified':  'color: %s;' % BLACK,
    'status.added':     'color: %s;' % BLACK,
    'status.removed':   'color: %s;' % BLACK,
    'status.missing':   'color: %s;' % BLACK,
    'status.unknown':   'color: %s;' % BLACK,
    'status.ignored':   'color: %s;' % BLACK,
    'status.clean':     'color: %s;' % BLACK,
    'status.copied':    'color: %s;' % BLACK,
}
