# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from twisted.python import log
import logging
from logging import DEBUG  # noqa


class LogFwd(object):
    @classmethod
    def write(cls, msg):
        log.msg(msg.rstrip())
        pass

    @classmethod
    def flush(cls):
        pass


def init(**kw):
    logging.basicConfig(stream=LogFwd,
                        format='%(name)s: (%(levelname)s) %(message)s')
    for k, v in kw.iteritems():
        logging.getLogger(k).setLevel(v)


def critical(cat, msg):
    logging.getLogger(cat).critical(msg)
    pass


def error(cat, msg):
    logging.getLogger(cat).error(msg)
    pass


def warning(cat, msg):
    logging.getLogger(cat).warning(msg)
    pass


def info(cat, msg):
    logging.getLogger(cat).info(msg)
    pass


def debug(cat, msg):
    logging.getLogger(cat).debug(msg)
    pass
