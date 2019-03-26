# -*- coding: utf-8 -*-
import asyncio
import datetime
import distutils.version
import os
import signal
import tempfile

import aiohttp
import jinja2

MINVER = distutils.version.LooseVersion('2017.7.0')
PATH = os.path.dirname(os.path.abspath(__file__))
with open(f'{PATH}/Dockerfile.j2') as dockerfile:
    DOCKERTEMPLATE = jinja2.Template(dockerfile.read())


class SaltVersion(object):

    loop = asyncio.get_event_loop()
    versions = []
    date = datetime.datetime.utcnow().strftime("%Y%M%d")

    def __init__(self, version):
        self.version = version

    async def __call__(self, force=False):
        try:
            tmpfile = tempfile.mkstemp()
            with open(tmpfile[1], 'w') as dfile:
                print(DOCKERTEMPLATE.render(salt_version=self.version), file=dfile)
            
            cwd = os.getcwd()
            if cwd != PATH:
                os.chdir(PATH)

            args = ['docker', 'build', '--file', tmpfile[1]]

            if force is True:
                args.append('--no-cache')

            args.extend([
                '--tag', f'gtmanfred/saltstack:{self.version}',
                '--tag', f'gtmanfred/saltstack:{self.version}-{self.date}',
                PATH
            ])

            proc = await asyncio.create_subprocess_exec(*args, loop=self.loop)
            await proc.communicate()
        finally:
            os.chdir(cwd)
            os.unlink(tmpfile[1])

    @classmethod
    async def build_salt_images(cls):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://pypi.org/pypi/salt/json') as response:
                data = await response.json()
        def check_version(version):
            if version < MINVER or 'rc' in version.version:
                return False
            if [
                    v for v in data['releases']
                    if distutils.version.LooseVersion(v).version[:-1] == version.version[:-1] and
                       distutils.version.LooseVersion(v) > version
            ]:
                return False
            return True
        versions = sorted(filter(check_version, map(distutils.version.LooseVersion, data['releases'])))
        for idx, version in enumerate(versions):
            if idx == 0:
                await SaltVersion(version)(force=False)
            else:
                cls.versions.append(cls.loop.create_task(cls(version)()))
        await asyncio.gather(*cls.versions, loop=cls.loop)


def main():
    loop = asyncio.get_event_loop()
    for signame in {'SIGINT', 'SIGTERM'}:
        loop.add_signal_handler(getattr(signal, signame), loop.stop)
    try:
        loop.run_until_complete(SaltVersion.build_salt_images())
    finally:
        loop.close()


if __name__ == '__main__':
    main()