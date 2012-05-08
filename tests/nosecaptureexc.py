"""Nose plugin to capture unhandled exception"""
import sys
from nose import plugins

class CaptureExcPlugin(plugins.Plugin):
    """Capture unhandled exception (probably raised inside event loop)"""
    enabled = False
    name = 'capture-exc'

    def options(self, parser, env):
        parser.add_option('--no-capture-exc', dest='capture_exc',
                          action='store_false', default=True,
                          help='Catch unhandled exception to report as error')

    def configure(self, options, conf):
        self.enabled = options.capture_exc

    def prepareTestResult(self, result):
        # dirty hack to access result.addError()
        self._result = result

    def startTest(self, test):
        self._origexcepthook = sys.excepthook
        sys.excepthook = self._excepthook
        self._excepts = []

    def stopTest(self, test):
        sys.excepthook = self._origexcepthook
        del self._origexcepthook
        if self._excepts:
            # BUG: because the corresponding addSuccess/Failure/Error for the
            # given test is already called, this increases the test counts.
            self._result.addError(test, self._excepts.pop(0))

    def _excepthook(self, type, value, traceback):
        self._excepts.append((type, value, traceback))
