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

    if 'addsitedir' in tac:
        p.exit('Slave already processed')

    tac = ("""import site
site.addsitedir('%s')

""" % os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'vendor-local')
    )
    + tac.replace('import BuildSlave', """import BuildSlave
import l10ninsp.slave""")
    )

    open(dest, 'w').write(tac)
