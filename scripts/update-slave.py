import optparse
import os.path


if __name__ == '__main__':
    p = optparse.OptionParser()
    (options, args) = p.parse_args()

    dest = args[0]
    if os.path.isdir(dest):
        dest = os.path.join(dest, 'buildbot.tac')
    if not os.path.isfile(dest):
        p.error('Slave not found at ' + args[0])

    tac = open(dest).read()

    if 'addsitedir' not in tac:
        tac = ("""import site
site.addsitedir('%s')

""" % os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'vendor-local'))
            + tac.replace('import BuildSlave', """import BuildSlave
import l10ninsp.slave""")
        )

        open(dest, 'w').write(tac)

    if 'django' not in tac:
        tac = tac.replace("""from twisted.application import service
""", """
import os
site.addsitedir('%s')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "buildbot_settings")
import django
django.setup()

from twisted.application import service
""" % os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'vendor-local')))

        open(dest, 'w').write(tac)
