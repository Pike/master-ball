import argparse
import os.path


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('master')
    args = p.parse_args()

    dest = args.master
    if os.path.isdir(dest):
        dest = os.path.join(dest, 'buildbot.tac')
    if not os.path.isfile(dest):
        p.error('Master not found at ' + args.master)

    tac = open(dest).read()

    if 'addsitedir' in tac:
        p.exit('Master already processed')

    tac = ("""import site
site.addsitedir('%s')
site.addsitedir('%s')

""" % (os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'vendor-local')
        ),
        os.path.abspath(
        os.path.dirname(__file__)
        ))
        + tac)

    open(dest, 'w').write(tac)
