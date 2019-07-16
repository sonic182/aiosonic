"""Utils for script."""
import os
import collections
import logging
from uuid import uuid4
from logging.handlers import TimedRotatingFileHandler


class LevelFilter(logging.Filter):
    def __init__(self, levels, name=''):
        super(LevelFilter, self).__init__(name)
        self.levels = levels

    def filter(self, record):
        return record.levelno in self.levels


class Logger(logging.LoggerAdapter):
    """Logger adapter."""

    def process(self, msg, kwargs):
        """Process log."""
        extra = self.extra.copy()
        data = kwargs.pop('extra', {})

        extra['uuid'] = extra.get('uuid', uuid4().hex)
        kwargs['extra'] = extra
        self.ignore = kwargs.pop('ignore', [])
        self.hidden = kwargs.pop('hidden', [])

        return msg + ' - ' + self._parse_data(data), kwargs

    def _parse_data(self, extra, key=''):
        """Append data params recursively.

        TODO: change to secuential implementation.
        """
        res = ''
        if isinstance(extra, dict):
            for _key, value in collections.OrderedDict(extra).items():
                temp_key = '{}{}{}'.format(key, ('.' if key else ''), _key)
                res += self._parse_data(value, temp_key)
        elif isinstance(extra, list):
            for ind, item in enumerate(extra):
                temp_key = '{}{}{}'.format(key, ('.' if key else ''), ind)
                res += self._parse_data(item, temp_key)
        else:
            return res + self.log_data(key, extra)
        return res

    def log_data(self, key, value):
        """Log data folowwing some rules."""
        if key in self.ignore:
            return ''
        elif key in self.hidden:
            return '{}={}'.format(key, ''.rjust(len(value), '*'))
        return '{}={}; '.format(key, value)


def get_logger(config, debug=False, verbose=False, uuid=uuid4().hex,
               name=__name__):
    """Setup logging."""
    fmt = logging.Formatter(
        '{asctime} - {module}:{lineno} - {levelname} - {uuid} - {msg}',
        style='{')
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if verbose:
        stream = logging.StreamHandler()
        stream.setLevel(level)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    file_levels = (
        ('debug.log', (logging.DEBUG,)),
        ('main.log', (logging.INFO,)),
        ('error.log', (logging.WARNING, logging.ERROR, logging.CRITICAL)),
    )

    filepath = config['logging'].get('path', './logs/')
    if not os.path.exists(filepath):
        os.makedirs(filepath)

    for filename, levels in file_levels:
        fileh = TimedRotatingFileHandler(filepath + filename)
        fileh.setFormatter(fmt)
        fileh.setLevel(level)
        fileh.addFilter(LevelFilter(levels))
        logger.addHandler(fileh)
    return Logger(logger, {'uuid': uuid}), uuid
