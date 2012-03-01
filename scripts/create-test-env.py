import optparse
import os
import os.path
import subprocess
import sys


ENVPATH = '@master'

def ensureCustomRepository(reponame, revision, hgcustom_orig, env_path):
    base = os.path.join(env_path, 'hgcustom')
    if not os.path.isdir(base):
        os.makedirs(base)
    if os.path.isdir(os.path.join(base, reponame, '.hg')):
        rv = subprocess.call(['hg', 'pull', '-r', revision],
                             cwd = os.path.join(base, reponame))
        if rv:
            raise RuntimeError("hg failed to pull hgcustom's %s" % reponame)
    else:
        rv = subprocess.call(['hg', 'clone', '--noupdate','--pull',
                              '%s/%s' % (hgcustom_orig, reponame)],
                               cwd = base)
        if rv:
            raise RuntimeError('hg failed to clone %s' % reponame)
    rv = subprocess.call(['hg', 'update', '-c', '-r', revision],
                         cwd = os.path.join(base, reponame))
    if rv:
        raise RuntimeError("hg failed to update -c hgcustom's %s" % reponame)


def ensureRepo(leaf, dest, env_path, push_l10n=True):
    base = os.path.join(dest, 'repos')
    if not os.path.isdir(base):
        os.makedirs(base)
    if os.path.isdir(os.path.join(base, leaf)):
        return

    os.makedirs(os.path.join(base, leaf))
    rv = subprocess.call(['hg', 'init', leaf], cwd = base)
    if rv:
        raise RuntimeError('Couldnt hg init %s' % leaf)
    tail = '''
[hooks]
pretxnchangegroup.a_singlehead = python:mozhghooks.single_head_per_branch.hook
pretxnchangegroup.z_linearhistory = python:mozhghooks.pushlog.log

[extensions]
pushlog-feed = %(env)s/hgcustom/pushlog/pushlog-feed.py
buglink = %(env)s/hgcustom/pushlog/buglink.py
hgwebjson = %(env)s/hgcustom/pushlog/hgwebjson.py
'''
    hgrc = open(os.path.join(base, leaf, '.hg', 'hgrc'), 'a')
    hgrc.write(tail % {'env': os.path.abspath(env_path)})
    hgrc.close()

    rv = subprocess.call(['hg', 'clone', leaf,
                          os.path.join('..', 'workdir', leaf)],
                         cwd=base)
    if rv:
        raise RuntimeError('clone for %s failed' % leaf)
    browserdir = os.path.join(dest, 'workdir', leaf, 'browser')
    if leaf.startswith('l10n'):
        # create initial content for l10n
        os.makedirs(browserdir)
        open(os.path.join(browserdir, 'file.properties'),
             'w').write('''k_e_y: %s value
''' % leaf)
    else:
        # create initial content for mozilla
        os.makedirs(os.path.join(browserdir, 'locales', 'en-US'))
        open(os.path.join(browserdir, 'locales', 'en-US', 'file.properties'),
             'w').write('''k_e_y: en-US value
''')
        open(os.path.join(browserdir, 'locales', 'all-locales'),
             'w').write('''ab
de
ja-JP-mac
x-testing
''')
        open(os.path.join(browserdir, 'locales', 'l10n.ini'),
             'w').write('''[general]
depth = ../..
all = browser/locales/all-locales

[compare]
dirs = browser
''')
    rv = subprocess.call(['hg', 'add', '.'], cwd=browserdir)
    if rv:
        raise RuntimeError('failed to add initial content')
    rv = subprocess.call(['hg', 'ci', '-mInitial commit for %s' % leaf],
                         cwd=browserdir)
    if rv:
        raise RuntimeError('failed to check in initian content to %s' %
                           leaf)
    if leaf.startswith('l10n') and not push_l10n:
        return
    rv = subprocess.call(['hg', 'push'], cwd=browserdir)
    if rv:
        raise RuntimeError('failed to push to %s' % leaf)


def createWebDir(dest, env_path):
    content = '''[collections]
repos = repos

[web]
style = gitweb_mozilla
templates = %(env)s/hgcustom/hg_templates
'''
    if not os.path.isfile(os.path.join(dest, 'webdir.conf')):
        open(os.path.join(dest, 'webdir.conf'),
             'w').write(content % {'dest': os.path.abspath(dest),
                                    'env': os.path.abspath(env_path)})

    
def createEnvironment(env_path, hgcustom_orig):
    '''Prepare a virtualenv to use for the following stages'''
    # pretend that env/bin/activate is good enough to check this
    if not os.path.isfile(os.path.join(env_path, 'bin', 'activate')):
        rv = subprocess.check_call(['virtualenv', env_path])
        if rv:
            raise RuntimeError("Failed to create virtualenv in " + env_path)
    hgcustom = {
        'hg_templates': '672340227bea',
        'hghooks': '1e7a365890ab',
        'pushlog': 'e99a36d3fd4a'
        }
    if not (hgcustom_orig.startswith('http://') or
            hgcustom_orig.startswith('https://')):
        hgcustom_orig = os.path.expanduser(hgcustom_orig)
        hgcustom_orig = os.path.abspath(hgcustom_orig)
    for name, rev in hgcustom.iteritems():
        ensureCustomRepository(name, rev, hgcustom_orig, env_path)


def setupEnvironment(env_path):
    '''Prepare a virtualenv to use for the following stages'''
    # pretend that env/bin/activate is good enough to check this
    rv = subprocess.check_call(['pip', 'install', '-r',
                                 os.path.join(env_path, '..', 'requirements.txt')])
    if rv:
        raise RuntimeError("Failed to install requirements in " + env_path)
    rv = subprocess.check_call(['python', 'setup.py', 'install'],
                               cwd=os.path.join(env_path, 'hgcustom', 'hghooks'))
    if rv:
        raise RuntimeError("Failed to install hghooks")


def setupWorkdir(dest, env_path, push_l10n=False):
    '''Set up the actual working directory for our repos'''
    downstreams = (
        'mozilla',
        'l10n/ab',
        'l10n/de',
        'l10n/ja-JP-mac',
        'l10n/x-testing',
    )
    if not os.path.isdir(os.path.join(dest, 'workdir', 'l10n')):
        os.makedirs(os.path.join(dest, 'workdir', 'l10n'))
    subprocess.check_call(['which','hg'], cwd=dest)

    for l in downstreams:
        ensureRepo(l, dest, env_path, push_l10n=push_l10n)

    createWebDir(dest, env_path)


if __name__ == "__main__":
    p = optparse.OptionParser()
    p.add_option('-v', dest='verbose', action='store_true')
    p.add_option('--hgcustom', default='http://hg.mozilla.org/hgcustom/')
    g = optparse.OptionGroup(p, 'Internal use',
                             'These options are to control the flow of the script itself')
    g.add_option('--stage', default='env',
                 help='Specify the stage to run [env|setup|repos]')
    p.add_option_group(g)
    (options, args) = p.parse_args()

    dest = args[0]
    def nextcmd(stage):
        rv = ['python', __file__]
        for k, v in options.__dict__.iteritems():
            if k == 'verbose':
                if v:
                    rv.append('-v')
            elif k == 'stage':
                rv.append('--stage=' + stage)
            else:
                rv.append('--%s=%s' % (k.replace('_', '-'), v))
        rv.append(dest)
        return rv

    nextstage = None
    env = os.environ.copy()
    print options.stage, sys.executable
    if options.stage == 'env':
        createEnvironment(ENVPATH, options.hgcustom)
        nextstage = 'setup'
        env['PATH'] = os.path.abspath(os.path.join(ENVPATH, 'bin')) + os.pathsep + env['PATH']
    elif options.stage == 'setup':
        setupEnvironment(ENVPATH)
        nextstage =  'repos'
    elif options.stage == 'repos':
        setupWorkdir(dest, ENVPATH)
        print 'done'
    if nextstage is not None:
        rv = subprocess.call(nextcmd(nextstage), env=env)
        if rv:
            raise RuntimeError('stage %s failed with %s' % (options.stage, str(rv)))
