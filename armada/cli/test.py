# Copyright 2017 The Armada Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import yaml

import click
from oslo_config import cfg

from armada.cli import CliAction
from armada import const
from armada.handlers.test import test_release_for_success
from armada.handlers.manifest import Manifest
from armada.handlers.tiller import Tiller
from armada.utils.release import release_prefixer

CONF = cfg.CONF


@click.group()
def test():
    """ Test Manifest Charts

    """


DESC = """
This command tests deployed charts.

The tiller command uses flags to obtain information from Tiller services.
The test command will run the release chart tests either via a the manifest or
by targeting a release.

To test Armada deployed releases:

    $ armada test --file examples/simple.yaml

To test release:

    $ armada test --release blog-1

"""

SHORT_DESC = "Command tests releases."


@test.command(name='test', help=DESC, short_help=SHORT_DESC)
@click.option('--file', help="Armada manifest.", type=str)
@click.option('--release', help="Helm release.", type=str)
@click.option('--tiller-host', help="Tiller host IP.", default=None)
@click.option(
    '--tiller-port',
    help="Tiller host port.",
    type=int,
    default=CONF.tiller_port)
@click.option(
    '--tiller-namespace',
    '-tn',
    help="Tiller Namespace.",
    type=str,
    default=CONF.tiller_namespace)
@click.option(
    '--target-manifest',
    help=("The target manifest to run. Required for specifying "
          "which manifest to run when multiple are available."),
    default=None)
@click.option(
    '--cleanup',
    help=("Delete test pods upon completion."),
    is_flag=True,
    default=None)
@click.option('--debug', help="Enable debug logging.", is_flag=True)
@click.pass_context
def test_charts(ctx, file, release, tiller_host, tiller_port, tiller_namespace,
                target_manifest, cleanup, debug):
    CONF.debug = debug
    TestChartManifest(ctx, file, release, tiller_host, tiller_port,
                      tiller_namespace, target_manifest,
                      cleanup).safe_invoke()


class TestChartManifest(CliAction):

    def __init__(self, ctx, file, release, tiller_host, tiller_port,
                 tiller_namespace, target_manifest, cleanup):

        super(TestChartManifest, self).__init__()
        self.ctx = ctx
        self.file = file
        self.release = release
        self.tiller_host = tiller_host
        self.tiller_port = tiller_port
        self.tiller_namespace = tiller_namespace
        self.target_manifest = target_manifest
        self.cleanup = cleanup

    def invoke(self):
        tiller = Tiller(
            tiller_host=self.tiller_host,
            tiller_port=self.tiller_port,
            tiller_namespace=self.tiller_namespace)
        known_release_names = [release[0] for release in tiller.list_charts()]

        if self.release:
            if not self.ctx.obj.get('api', False):
                self.logger.info("RUNNING: %s tests", self.release)
                success = test_release_for_success(
                    tiller, self.release, cleanup=self.cleanup)
                if success:
                    self.logger.info("PASSED: %s", self.release)
                else:
                    self.logger.info("FAILED: %s", self.release)
            else:
                client = self.ctx.obj.get('CLIENT')
                query = {
                    'tiller_host': self.tiller_host,
                    'tiller_port': self.tiller_port,
                    'tiller_namespace': self.tiller_namespace
                }
                resp = client.get_test_release(
                    release=self.release, query=query)

                self.logger.info(resp.get('result'))
                self.logger.info(resp.get('message'))

        if self.file:
            if not self.ctx.obj.get('api', False):
                documents = list(yaml.safe_load_all(open(self.file).read()))
                armada_obj = Manifest(
                    documents,
                    target_manifest=self.target_manifest).get_manifest()
                prefix = armada_obj.get(const.KEYWORD_ARMADA).get(
                    const.KEYWORD_PREFIX)

                for group in armada_obj.get(const.KEYWORD_ARMADA).get(
                        const.KEYWORD_GROUPS):
                    for ch in group.get(const.KEYWORD_CHARTS):
                        chart = ch['chart']
                        release_name = release_prefixer(
                            prefix, chart.get('release'))

                        if release_name in known_release_names:
                            cleanup = self.cleanup
                            if cleanup is None:
                                test_chart_override = chart.get('test', {})
                                if isinstance(test_chart_override, bool):
                                    self.logger.warn(
                                        'Boolean value for chart `test` key is'
                                        ' deprecated and support for this will'
                                        ' be removed. Use `test.enabled` '
                                        'instead.')
                                    # Use old default value.
                                    cleanup = True
                                else:
                                    cleanup = test_chart_override.get(
                                        'options', {}).get('cleanup', False)
                            self.logger.info('RUNNING: %s tests', release_name)
                            success = test_release_for_success(
                                tiller, release_name, cleanup=cleanup)
                            if success:
                                self.logger.info("PASSED: %s", release_name)
                            else:
                                self.logger.info("FAILED: %s", release_name)

                        else:
                            self.logger.info('Release %s not found - SKIPPING',
                                             release_name)
            else:
                client = self.ctx.obj.get('CLIENT')
                query = {
                    'tiller_host': self.tiller_host,
                    'tiller_port': self.tiller_port,
                    'tiller_namespace': self.tiller_namespace
                }

                with open(self.filename, 'r') as f:
                    resp = client.get_test_manifest(
                        manifest=f.read(), query=query)
                    for test in resp.get('tests'):
                        self.logger.info('Test State: %s', test)
                        for item in test.get('tests').get(test):
                            self.logger.info(item)

                    self.logger.info(resp)
