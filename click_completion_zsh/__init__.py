from os import environ
from re import match
from re import sub
from typing import Any
from typing import Optional

from click import Command
from click import Context
from click import MultiCommand
from click import ParamType
from click.shell_completion import add_completion_class


__all__ = ('init',)


def quote(
    value: str,
    embed: bool = False,
    double: bool = False,
) -> str:
    if match('^[A-Za-z0-9_+-]*$', value):
        return value

    if double:
        value = sub(r'([!$\\"`])', r'\\\1', value)
    else:
        value = value.replace("'", "'\\''")

    if embed:
        return value
    else:
        quote = '"' if double else "'"
        return f'{quote}{value}{quote}'


def get_help(
    param: dict[str, Any],
) -> Optional[str]:
    help = param.get('short_help')
    if help is None:
        help = param.get('help')
    if help is None:
        return None

    assert isinstance(help, str)

    if param['name'] == 'help':
        return 'display usage information'

    help = help.rstrip('.')
    first_word = help.split(' ')[0]
    if all(not c.isupper() for c in first_word[1:]):
        help = f'{help[0].lower()}{help[1:]}'

    return help


def complete(
    info: dict[str, Any],
) -> str:
    lines = [
        f'#compdef {info["command"]["name"]}',
        '',
    ]
    if 'commands' in info['command']:
        lines.extend((
            'local curcontext="$curcontext" state state_descr line',
            'typeset -A opt_args',
            '',
        ))

    lines.extend(complete_command(info['command'], info['allow_interspersed_args']))
    return ''.join(f'{line}\n' for line in lines)


def complete_command(
    command: dict[str, Any],
    allow_interspersed_args: bool,
) -> list[str]:
    lines = []

    line = '_arguments -s -S'
    if not allow_interspersed_args:
        line += ' -A \'-*\''
    if 'commands' in command:
        line += ' -C'
    line += ' : \\'
    lines.append(line)

    specs = []
    arg_count = 0
    has_variadic = False
    for param in command['params']:
        if param['param_type_name'] == 'option':
            spec = '\''

            all_names = [*param['opts'], *param['secondary_opts']]

            if param['multiple'] or param['count']:
                spec += '*'
            elif len(all_names) > 1:
                spec += f'({" ".join(quote(opt, embed=True) for opt in all_names)})'

            if len(all_names) == 1:
                spec += quote(all_names[0], True)
            else:
                spec += f'\'{{{",".join(quote(opt) for opt in all_names)}}}\''

            help = get_help(param)
            if help is not None:
                spec += f'[{quote(help, embed=True)}]'
            if not (param['is_flag'] or param['count']):
                argspec = complete_type(param['type'], param['name'], param['default'])
                # Tuple repatition is handled in complete_type
                count = 1 if param['type']['param_type'] == 'Tuple' else param['nargs']
                spec += ' '.join([argspec] * count)

            spec += '\''

            specs.append(spec)

        elif param['param_type_name'] == 'argument':
            if has_variadic:
                continue
            arg_count += 1
            spec = '\''
            if param['nargs'] == -1:
                spec += '*'
                has_variadic = True
            spec += complete_type(param['type'], param['name'], param['default'])
            spec += '\''
            count = 1 if param['nargs'] == -1 else param['nargs']
            specs.extend([spec] * count)

        else:
            raise ValueError(f'Unexpected param_type_name {param["param_type_name"]}')  # pragma: no cover

    if 'commands' in command:
        subcommands = []
        for name, subcommand in command['commands'].items():
            help = get_help(subcommand)
            if help is not None:
                subcommands.append(f'{quote(name, double=True)}\\:{quote(help, double=True)}')
            else:
                subcommands.append(quote(name, double=True))
        specs.append(f'\':subcommand:(({" ".join(subcommands)}))\'')
        specs.append('\'*::: := ->subcmd\' && return 0')

    lines.extend(f'  {spec} \\' for spec in specs[:-1])
    lines.append(f'  {specs[-1]}')

    if 'commands' in command:
        lines.append('')
        lines.append(f'service=$line[{arg_count + 1}]')
        lines.append('curcontext=${curcontext%:*}-$service:')
        lines.append('case $service in')

        for name, subcommand in command['commands'].items():
            lines.append(f'  {quote(name)})')
            lines.extend(f'    {line}' for line in complete_command(subcommand, allow_interspersed_args))
            lines.append('  ;;')

        lines.append('esac')

    return lines


def complete_type(
    param: dict[str, Any],
    name: str,
    default: Optional[Any],
) -> str:
    param_type = param['param_type']

    # Strip trailing _ used to work around reserved words.
    message = name[:-1] if name[-1] == '_' else name

    if default is not None:
        message += f' [{default}]'

    if param_type == 'Bool':
        return f':{message}:(0 1 false true f t no yes n y off on)'

    if param_type == 'Choice':
        return f':{message}:({" ".join(quote(c, double=True) for c in param["choices"])})'

    if param_type == 'File':
        return f':{message}:_files'

    if param_type == 'Path':
        only_dirs = param['file_okay'] is False and param['dir_okay'] is True
        return f':{message}:_files{" -/" if only_dirs else ""}'

    if param_type in ('IntRange', 'FloatRange'):
        action = '_numbers'
        if param_type == 'FloatRange':
            action += ' -f'
        if default is not None:
            action += f' -d {default}'
        if param['min'] is not None:
            min_value = param['min']
            if param_type == 'IntRange' and param['min_open']:
                min_value += 1
            action += f' -l {min_value}'
        if param['max'] is not None:
            max_value = param['max']
            if param_type == 'IntRange' and param['max_open']:
                max_value -= 1
            action += f' -m {max_value}'
        action += ' ' + quote(name, double=True)
        return f': :{action}'

    if param_type == 'Tuple':
        return ' '.join(complete_type(argument, name, None)
                        for argument in param['types'])

    return f':{message}:'


def find_param_type(
    name: str,
    ctx: Context,
    command: Command,
) -> Optional[ParamType]:
    for param in command.get_params(ctx):
        if param.type.name == name:
            return param.type

    if isinstance(command, MultiCommand):
        for subcommand_name in command.list_commands(ctx):
            subcommand = command.get_command(ctx, subcommand_name)
            if subcommand is None:
                continue  # pragma: no cover
            result = find_param_type(name, ctx, subcommand)
            if result is not None:
                return result

    return None


class Zsh2Complete:
    name = 'zsh2'

    def __init__(
        self,
        cli: Command,
        ctx_args: dict[str, Any],
        prog_name: str,
        complete_var: str,
    ) -> None:
        self.cli = cli
        self.ctx_args = ctx_args
        self.prog_name = prog_name
        self.complete_var = complete_var

    def make_context(self) -> Context:
        return self.cli.make_context(self.prog_name, [], **self.ctx_args,
                                     resilient_parsing=True)

    def source(self) -> str:
        """Produce the completion script."""
        with self.make_context() as ctx:
            info = ctx.to_info_dict()
        return complete(info)

    def complete(self) -> str:
        """Produce completions for a type."""
        with self.make_context() as ctx:
            param_type = find_param_type(environ['COMP_TYPE'], ctx, ctx.command)
            if param_type is None:
                return ''
            completions = param_type.shell_complete(ctx, None, '')
        return '\0'.join(f'{x.value}\0{x.help if x.help is not None else ""}'
                         for x in completions)


def init() -> None:
    # Zsh2Complete doesn't inherit from ShellComplete, but the duck type
    # matches.
    add_completion_class(Zsh2Complete, 'zsh2')  # type: ignore
