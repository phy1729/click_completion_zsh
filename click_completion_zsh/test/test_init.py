from os import environ
from textwrap import dedent

import click
from click import Context
from click import ParamType
from click import Parameter
from click.shell_completion import CompletionItem
from click.shell_completion import get_completion_class

from .. import Zsh2Complete
from .. import find_param_type
from .. import get_help
from .. import init
from .. import quote


def test_quote() -> None:
    assert quote('foo_bar') == 'foo_bar'
    assert quote('foo bar') == "'foo bar'"
    assert quote("foo's bar") == "'foo'\\''s bar'"
    assert quote('foo_bar', double=True) == 'foo_bar'
    assert quote('foo bar', double=True) == '"foo bar"'
    assert quote('$(foo "bar" `baz`', double=True) == r'"\$(foo \"bar\" \`baz\`"'
    assert quote("foo's bar", embed=True) == "foo'\\''s bar"


def test_get_help() -> None:
    assert get_help({}) is None
    assert get_help({
        'name': 'help',
        'param_type_name': 'option',
        'opts': ['--help'],
        'secondary_opts': [],
        'type': {
            'param_type': 'Bool',
            'name': 'boolean',
        },
        'required': False,
        'nargs': 1,
        'multiple': False,
        'default': False,
        'envvar': None,
        'help': 'Show this message and exit.',
        'prompt': None,
        'is_flag': True,
        'flag_value': True,
        'count': False,
        'hidden': False,
    }) == 'display usage information'
    assert get_help({
        'name': 'verbose',
        'opts': ['--verbose'],
        'help': 'Be more verbose.'
    }) == 'be more verbose'
    assert get_help({
        'name': 'foo',
        'help': 'Some long description goes here.',
        'short_help': 'Concise text.',
    }) == 'concise text'
    assert get_help({
        'name': 'hostname',
        'help': 'LDAP hostname.',
    }) == 'LDAP hostname'


def test_options() -> None:
    # Cases from https://click.palletsprojects.com/en/8.0.x/options/
    for decorator, line in (
        (click.option('--n', default=1), '--n:n [1]:'),
        (click.option('--n', required=True, type=int), '--n:n:'),
        (click.option('--from', '-f', 'from_'), '(--from -f)\'{--from,-f}\':from:'),
        (click.option('--to', '-t'), '(--to -t)\'{--to,-t}\':to:'),
        (click.option('--pos', nargs=2, type=float), '--pos:pos: :pos:'),
        (click.option('--item', type=(str, int)), '--item:item: :item:'),
        (click.option('--message', '-m', multiple=True), '*\'{--message,-m}\':message:'),
        (click.option('-v', '--verbose', count=True), '*\'{-v,--verbose}\''),
        (click.option('--shout/--no-shout', default=False), '(--shout --no-shout)\'{--shout,--no-shout}\''),
        (click.option('--shout', is_flag=True), '--shout'),
        (click.option('--shout/--no-shout', ' /-S', default=False), '(--shout --no-shout -S)\'{--shout,--no-shout,-S}\''),
        (click.option('--hash-type', type=click.Choice(['MD5', 'SHA1'], case_sensitive=False)), '--hash-type:hash_type:(MD5 SHA1)'),
        (click.option('--name', prompt=True), '--name:name:'),
        (click.password_option(), '--password:password:'),
        (click.confirmation_option(prompt='Are you sure you want to drop the db?'), '--yes[confirm the action without prompting]'),
        (click.option('+w/-w'), '(+w -w)\'{+w,-w}\''),
        (click.option("--count", type=click.IntRange(0, 20, clamp=True)), '--count: :_numbers -l 0 -m 20 count'),
        (click.option("--digit", type=click.IntRange(0, 9)), '--digit: :_numbers -l 0 -m 9 digit'),
        # XXX mark optional
        (click.option("--name", is_flag=False, flag_value="Flag", default="Default"), '--name:name [Default]:'),
    ):
        @click.command()
        @decorator
        def cli() -> None:
            """Dummy command for testing."""

        assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
                #compdef cli

                _arguments -s -S : \
                  ''' + f"'{line}'" + r''' \
                  '--help[display usage information]'
                ''')[1:]


def test_arguments() -> None:
    # Cases from https://click.palletsprojects.com/en/8.0.x/arguments/
    for decorator, line in (
        (click.argument('filename'), ':filename:'),
        (click.argument('src', nargs=-1), '*:src:'),
        (click.argument('input', type=click.File('rb')), ':input:_files'),
        (click.argument('filename', type=click.Path(exists=True)), ':filename:_files'),
    ):
        @click.command()
        @decorator
        def cli() -> None:
            """Dummy command for testing."""

        assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
                #compdef cli

                _arguments -s -S : \
                  ''' + f"'{line}'" + r''' \
                  '--help[display usage information]'
                ''')[1:]


def test_types() -> None:
    for decorator, line in (
        (click.argument('light', type=click.BOOL), ':light:(0 1 false true f t no yes n y off on)'),
        (click.argument('rotation', type=click.FloatRange(0, 360), default=0), ': :_numbers -f -d 0 -l 0 -m 360 rotation'),
        (click.argument('hour', type=click.IntRange(0, 24, max_open=True)), ': :_numbers -l 0 -m 23 hour'),
        (click.argument('rate', type=click.IntRange(0, 100, min_open=True)), ': :_numbers -l 1 -m 100 rate'),
        (click.argument('score', type=click.IntRange(0)), ': :_numbers -l 0 score'),
        (click.argument('grav_potential', type=click.IntRange(max=0)), ': :_numbers -m 0 grav_potential'),
        (click.argument('file', type=click.File('r'), default='foo'), ':file [foo]:_files'),
        (click.argument('dir', type=click.Path(file_okay=False)), ':dir:_files -/'),
    ):
        @click.command()
        @decorator
        def cli() -> None:
            """Dummy command for testing."""

        assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
                #compdef cli

                _arguments -s -S : \
                  ''' + f"'{line}'" + r''' \
                  '--help[display usage information]'
                ''')[1:]


def test_command_name() -> None:
    @click.command()
    def cli() -> None:
        """Dummy command for testing."""

    assert Zsh2Complete(cli, {}, 'name', '').source() == dedent(r'''
            #compdef name

            _arguments -s -S : \
              '--help[display usage information]'
            ''')[1:]


def test_option_needs_quoting() -> None:
    @click.command()
    @click.option('--terrible', '-$')
    def cli() -> None:
        """Dummy command for testing."""

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            _arguments -s -S : \
              '(--terrible -$)'{--terrible,'-$'}':terrible:' \
              '--help[display usage information]'
            ''')[1:]


def test_option_non_dash_prefix() -> None:
    @click.command(context_settings={'allow_interspersed_args': False})
    @click.option('+w/-w')
    def cli() -> None:
        """Dummy command for testing."""

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            _arguments -s -S -A '[+-]*' : \
              '(+w -w)'{+w,-w}'' \
              '--help[display usage information]'
            ''')[1:]


def test_option_bracket_in_help() -> None:
    @click.command()
    @click.option('--test', help='test suite [default: default]')
    def cli() -> None:
        """Dummy command for testing."""

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            _arguments -s -S : \
              '--test[test suite \[default: default\]]:test:' \
              '--help[display usage information]'
            ''')[1:]


def test_command_variadic() -> None:
    @click.command()
    @click.argument('src', nargs=-1, type=click.File('r'))
    @click.argument('dest', nargs=1, type=click.File('w'))
    def cli() -> None:
        """Dummy command for testing."""

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            _arguments -s -S : \
              '*:src:_files' \
              '--help[display usage information]'
            ''')[1:]


def test_command_subcommands() -> None:
    @click.group()
    @click.option('-v', '--verbose', count=True, help='Increase verbosity.')
    def cli() -> None:
        """Dummy command for testing."""

    @cli.command()
    @click.option('-b', '--bar', help='bar\'s help')
    def foo() -> None:
        """Foo subcommand help."""

    @cli.command()
    @click.option('--foo', default=1, help='foo help')
    def bar() -> None:
        pass  # pragma: no cover

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            local curcontext="$curcontext" state state_descr line
            typeset -A opt_args

            _arguments -s -S -A '-*' -C : \
              '*'{-v,--verbose}'[increase verbosity]' \
              '--help[display usage information]' \
              ':subcommand:((bar foo\:"foo subcommand help"))' \
              '*::: := ->subcmd' && return 0

            service=$line[1]
            curcontext=${curcontext%:*}-$service:
            case $service in
              bar)
                _arguments -s -S -A '-*' : \
                  '--foo[foo help]:foo [1]:' \
                  '--help[display usage information]'
              ;;
              foo)
                _arguments -s -S -A '-*' : \
                  '(-b --bar)'{-b,--bar}'[bar'\''s help]:bar:' \
                  '--help[display usage information]'
              ;;
            esac
            ''')[1:]


def test_command_subcommand_after_arg() -> None:
    @click.group()
    @click.argument('arg')
    def cli() -> None:
        """Dummy command for testing."""

    @cli.command()
    @click.argument('foo')
    def foo() -> None:
        """Foo."""

    @cli.command()
    @click.argument('bar')
    def bar() -> None:
        """Bar."""

    assert Zsh2Complete(cli, {}, 'cli', '').source() == dedent(r'''
            #compdef cli

            local curcontext="$curcontext" state state_descr line
            typeset -A opt_args

            _arguments -s -S -A '-*' -C : \
              ':arg:' \
              '--help[display usage information]' \
              ':subcommand:((bar\:bar foo\:foo))' \
              '*::: := ->subcmd' && return 0

            service=$line[2]
            curcontext=${curcontext%:*}-$service:
            case $service in
              bar)
                _arguments -s -S -A '-*' : \
                  ':bar:' \
                  '--help[display usage information]'
              ;;
              foo)
                _arguments -s -S -A '-*' : \
                  ':foo:' \
                  '--help[display usage information]'
              ;;
            esac
            ''')[1:]


def test_find_param_type() -> None:
    class TestType(ParamType):
        name = 'test'

    @click.group()
    @click.argument('arg')
    def cli() -> None:
        """Dummy command for testing."""

    @cli.command()
    @click.argument('foo')
    def foo() -> None:
        """Foo."""

    @cli.group()
    @click.argument('bar')
    def bar() -> None:
        """Bar."""

    @bar.command()
    @click.argument('baz', type=TestType())
    def baz() -> None:
        """Baz."""

    with Context(cli) as ctx:
        assert isinstance(find_param_type('test', ctx, cli), TestType)
        assert find_param_type('text', ctx, cli) is click.STRING
        # While bool is a valid type defined by click, since it is not used by the
        # test command, it should not be found.
        assert find_param_type('bool', ctx, cli) is None


def test_complete() -> None:
    class TestType(ParamType):
        name = 'test'

        def shell_complete(
            self,
            ctx: Context,
            param: Parameter,
            incomplete: str
        ) -> list[CompletionItem]:
            return [CompletionItem(x, help=f'{x} help')
                    for x in ('foo', 'bar', 'baz')
                    if x.startswith(incomplete)]

    @click.command()
    @click.argument('arg', type=TestType())
    def cli() -> None:
        """Dummy command for testing."""

    environ['COMP_TYPE'] = 'test'
    assert Zsh2Complete(cli, {}, 'cli', '').complete() == (
        'foo\0foo help\0'
        'bar\0bar help\0'
        'baz\0baz help'
    )

    environ['COMP_TYPE'] = 'does_not_exist'
    assert Zsh2Complete(cli, {}, 'cli', '').complete() == ''


def test_init() -> None:
    init()
    assert get_completion_class('zsh2') is Zsh2Complete  # type: ignore
