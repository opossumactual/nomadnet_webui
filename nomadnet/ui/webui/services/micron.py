"""
Micron Markup to HTML Converter

Converts NomadNet's Micron markup language to HTML for web display.
"""

import re
import html
from typing import Optional, Tuple, List, Dict, Any


class MicronParser:
    """Parses Micron markup and converts to HTML"""

    def __init__(self, destination: str = "", path: str = "/"):
        self.destination = destination
        self.path = path
        self.form_id = 0

    def parse(self, markup: str, fg_color: Optional[str] = None, bg_color: Optional[str] = None) -> str:
        """
        Parse Micron markup and return HTML.

        Args:
            markup: Raw Micron markup text
            fg_color: Default foreground color (from #!fg= header)
            bg_color: Default background color (from #!bg= header)

        Returns:
            HTML string
        """
        # Extract color headers if present
        lines = markup.split('\n')
        content_lines = []

        for line in lines:
            if line.startswith('#!fg='):
                fg_color = line[5:].strip()
            elif line.startswith('#!bg='):
                bg_color = line[5:].strip()
            elif line.startswith('#!c='):
                # Cache control - ignore for now
                pass
            else:
                content_lines.append(line)

        # Parse state
        state = {
            'literal': False,
            'depth': 0,
            'fg_color': fg_color or 'inherit',
            'bg_color': bg_color or 'inherit',
            'bold': False,
            'underline': False,
            'italic': False,
            'align': 'left',
            'default_fg': fg_color or 'inherit',
            'default_bg': bg_color or 'inherit',
            'radio_groups': {},
        }

        html_parts = []
        self.form_id += 1

        # Wrap in a form for field submission
        html_parts.append(f'<form id="micron-form-{self.form_id}" class="micron-form" method="post">')

        for line in content_lines:
            html_line = self._parse_line(line, state)
            if html_line is not None:
                html_parts.append(html_line)

        html_parts.append('</form>')

        # Apply page-level styles
        style_parts = []
        if bg_color:
            style_parts.append(f'background-color: #{self._expand_color(bg_color)};')
        if fg_color:
            style_parts.append(f'color: #{self._expand_color(fg_color)};')

        if style_parts:
            wrapper_style = ' '.join(style_parts)
            return f'<div class="micron-page" style="{wrapper_style}">{"".join(html_parts)}</div>'
        else:
            return f'<div class="micron-page">{"".join(html_parts)}</div>'

    def _parse_line(self, line: str, state: Dict[str, Any]) -> Optional[str]:
        """Parse a single line of Micron markup"""
        if not line:
            return '<div class="micron-line">&nbsp;</div>'

        first_char = line[0] if line else ''

        # Check for literal mode toggle
        if line == '`=':
            state['literal'] = not state['literal']
            return None

        # In literal mode, just escape and return
        if state['literal']:
            if line == '\\`=':
                line = '`='
            return f'<pre class="micron-literal">{html.escape(line)}</pre>'

        # Check for escape
        if first_char == '\\':
            line = line[1:]
            return self._make_text_line(line, state)

        # Check for comments
        if first_char == '#':
            return None

        # Check for section depth reset
        if first_char == '<':
            state['depth'] = 0
            return self._parse_line(line[1:], state)

        # Check for headings
        if first_char == '>':
            depth = 0
            while depth < len(line) and line[depth] == '>':
                depth += 1
            state['depth'] = depth

            heading_text = line[depth:]
            if not heading_text:
                return None

            level = min(depth, 3)
            content = self._parse_inline(heading_text, state)
            return f'<h{level} class="micron-heading micron-h{level}">{content}</h{level}>'

        # Check for horizontal divider
        if first_char == '-' and len(line) <= 2:
            return '<hr class="micron-divider">'

        # Regular text line
        return self._make_text_line(line, state)

    def _make_text_line(self, line: str, state: Dict[str, Any]) -> str:
        """Create a text line with inline formatting"""
        content = self._parse_inline(line, state)
        indent = state['depth'] * 1.5  # em units
        align = state['align']

        style_parts = []
        if indent > 0:
            style_parts.append(f'margin-left: {indent}em;')
        if align != 'left':
            style_parts.append(f'text-align: {align};')

        style = f' style="{" ".join(style_parts)}"' if style_parts else ''
        return f'<div class="micron-line"{style}>{content}</div>'

    def _parse_inline(self, text: str, state: Dict[str, Any]) -> str:
        """Parse inline formatting, links, and fields"""
        output = []
        i = 0
        escape = False
        current_text = ''

        while i < len(text):
            c = text[i]

            if escape:
                current_text += c
                escape = False
                i += 1
                continue

            if c == '\\':
                escape = True
                i += 1
                continue

            if c == '`':
                # Output accumulated text
                if current_text:
                    output.append(self._styled_text(current_text, state))
                    current_text = ''

                # Parse formatting command
                i += 1
                if i >= len(text):
                    break

                i = self._parse_formatting(text, i, state, output)
                continue

            current_text += c
            i += 1

        # Output remaining text
        if current_text:
            output.append(self._styled_text(current_text, state))

        return ''.join(output)

    def _parse_formatting(self, text: str, i: int, state: Dict[str, Any], output: List[str]) -> int:
        """Parse formatting commands after backtick"""
        c = text[i]

        # Formatting toggles
        if c == '_':
            state['underline'] = not state['underline']
            return i + 1
        elif c == '!':
            state['bold'] = not state['bold']
            return i + 1
        elif c == '*':
            state['italic'] = not state['italic']
            return i + 1

        # Foreground color
        elif c == 'F' and i + 3 < len(text):
            state['fg_color'] = text[i+1:i+4]
            return i + 4
        elif c == 'f':
            state['fg_color'] = state['default_fg']
            return i + 1

        # Background color
        elif c == 'B' and i + 3 < len(text):
            state['bg_color'] = text[i+1:i+4]
            return i + 4
        elif c == 'b':
            state['bg_color'] = state['default_bg']
            return i + 1

        # Reset all formatting
        elif c == '`':
            state['bold'] = False
            state['underline'] = False
            state['italic'] = False
            state['fg_color'] = state['default_fg']
            state['bg_color'] = state['default_bg']
            state['align'] = 'left'
            return i + 1

        # Alignment
        elif c == 'c':
            state['align'] = 'center'
            return i + 1
        elif c == 'l':
            state['align'] = 'left'
            return i + 1
        elif c == 'r':
            state['align'] = 'right'
            return i + 1
        elif c == 'a':
            state['align'] = 'left'
            return i + 1

        # Field
        elif c == '<':
            return self._parse_field(text, i + 1, state, output)

        # Link
        elif c == '[':
            return self._parse_link(text, i + 1, state, output)

        return i + 1

    def _parse_field(self, text: str, start: int, state: Dict[str, Any], output: List[str]) -> int:
        """Parse form field: `<fieldname`> or `<width^fieldname`data> or `<^|name|value|*`label>"""
        # Find closing `>
        backtick_pos = text.find('`', start)
        if backtick_pos == -1:
            return start

        gt_pos = text.find('>', backtick_pos)
        if gt_pos == -1:
            return start

        field_spec = text[start:backtick_pos]
        field_data = text[backtick_pos + 1:gt_pos]

        # Parse field spec
        field_type = 'text'
        field_masked = False
        field_width = 24
        field_name = field_spec
        field_value = ''
        field_prechecked = False

        if '|' in field_spec:
            # Format: flags|name|value|* for radio/checkbox
            parts = field_spec.split('|')
            flags = parts[0]
            field_name = parts[1] if len(parts) > 1 else ''
            field_value = parts[2] if len(parts) > 2 else ''
            field_prechecked = len(parts) > 3 and parts[3] == '*'

            # Check for field type
            if '^' in flags:
                field_type = 'radio'
                flags = flags.replace('^', '')
            elif '?' in flags:
                field_type = 'checkbox'
                flags = flags.replace('?', '')
            elif '!' in flags:
                field_masked = True
                flags = flags.replace('!', '')

            # Check for width
            if flags:
                try:
                    field_width = min(int(flags), 256)
                except ValueError:
                    pass
        elif '^' in field_spec:
            # Format: width^fieldname for text field with width
            # e.g., 24^name means width=24, name=name
            parts = field_spec.split('^')
            if len(parts) == 2:
                try:
                    field_width = min(int(parts[0]), 256) if parts[0] else 24
                except ValueError:
                    pass
                field_name = parts[1]
        elif '!' in field_spec:
            # Masked field: !fieldname
            field_masked = True
            field_name = field_spec.replace('!', '')

        # Generate HTML
        input_name = f'field_{field_name}'

        if field_type == 'radio':
            checked = ' checked' if field_prechecked else ''
            label = html.escape(field_data) if field_data else field_value
            output.append(
                f'<label class="micron-radio">'
                f'<input type="radio" name="{html.escape(input_name)}" '
                f'value="{html.escape(field_value or field_data)}"{checked}>'
                f' {label}</label>'
            )
        elif field_type == 'checkbox':
            checked = ' checked' if field_prechecked else ''
            label = html.escape(field_data) if field_data else field_value
            output.append(
                f'<label class="micron-checkbox">'
                f'<input type="checkbox" name="{html.escape(input_name)}" '
                f'value="{html.escape(field_value or "on")}"{checked}>'
                f' {label}</label>'
            )
        else:
            input_type = 'password' if field_masked else 'text'
            # Check if it's a multiline field (has > in the width flags)
            if '>' in field_spec.split('|')[0] if '|' in field_spec else False:
                output.append(
                    f'<textarea name="{html.escape(input_name)}" '
                    f'class="micron-field micron-textarea" '
                    f'style="width: {field_width}ch;">{html.escape(field_data)}</textarea>'
                )
            else:
                output.append(
                    f'<input type="{input_type}" name="{html.escape(input_name)}" '
                    f'value="{html.escape(field_data)}" '
                    f'class="micron-field" style="width: {field_width}ch;">'
                )

        return gt_pos + 1

    def _parse_link(self, text: str, start: int, state: Dict[str, Any], output: List[str]) -> int:
        """Parse link: `[url`] or `[label`url`] or `[label`url`fields`]"""
        # Find closing ]
        end_pos = text.find(']', start)
        if end_pos == -1:
            return start

        link_data = text[start:end_pos]
        parts = link_data.split('`')

        if len(parts) == 1:
            link_label = parts[0]
            link_url = parts[0]
            link_fields = ''
        elif len(parts) == 2:
            link_label = parts[0]
            link_url = parts[1]
            link_fields = ''
        else:
            link_label = parts[0]
            link_url = parts[1]
            link_fields = parts[2]

        if not link_url:
            return end_pos + 1

        if not link_label:
            link_label = link_url

        # Convert link URL to web URL
        href = self._convert_link_url(link_url)

        # Check if this is an external link
        is_external = link_url.startswith('::')

        # Check if this is a submit link (only if it has field references to submit)
        is_submit = bool(link_fields) and not is_external

        if is_submit:
            # Create a submit button that posts the form
            field_inputs = ''
            if link_fields:
                for f in link_fields.split('|'):
                    if f:
                        field_inputs += f'<input type="hidden" name="__link_field" value="{html.escape(f)}">'

            output.append(
                f'<button type="submit" formaction="{html.escape(href)}" '
                f'class="micron-link micron-submit">{html.escape(link_label)}</button>'
                f'{field_inputs}'
            )
        else:
            # Regular link
            styled = self._styled_text(link_label, state, is_link=True)
            target = ' target="_blank" rel="noopener"' if is_external else ''
            output.append(f'<a href="{html.escape(href)}" class="micron-link"{target}>{styled}</a>')

        return end_pos + 1

    def _convert_link_url(self, url: str) -> str:
        """Convert Micron link URL to web URL"""
        if url.startswith('::'):
            # External URL with :: prefix
            return url[2:]
        elif url.startswith('https://') or url.startswith('http://'):
            # External URL without :: prefix
            return url
        elif url.startswith('lxmf@'):
            # LXMF address - link to conversations
            lxmf_hash = url[5:]
            return f'/conversations/{lxmf_hash}'
        elif url.startswith(':/'):
            # Local page on same node (:/path format)
            path = url[2:]
            if self.destination:
                return f'/browse/{self.destination}/{path}'
            else:
                return f'/browse/local/{path}'
        elif url.startswith(':'):
            # Remote node with : prefix
            # Format: :hash:/path or :hash:path
            rest = url[1:]
            if ':/' in rest:
                dest, path = rest.split(':/', 1)
                return f'/browse/{dest}/{path}'
            elif ':' in rest:
                dest, path = rest.split(':', 1)
                return f'/browse/{dest}/{path}'
            else:
                return f'/browse/{rest}/'
        elif ':/page/' in url or ':/file/' in url:
            # Remote node without : prefix (hash:/page/... format)
            dest, path = url.split(':/', 1)
            return f'/browse/{dest}/{path}'
        else:
            # Relative path
            return f'/browse/{self.destination}/{url}' if self.destination else f'/browse/local/{url}'

    def _styled_text(self, text: str, state: Dict[str, Any], is_link: bool = False) -> str:
        """Apply current styling to text"""
        escaped = html.escape(text)

        styles = []
        classes = ['micron-text']

        if state['bold']:
            styles.append('font-weight: bold;')
        if state['underline']:
            styles.append('text-decoration: underline;')
        if state['italic']:
            styles.append('font-style: italic;')

        if state['fg_color'] and state['fg_color'] != 'inherit':
            color = self._expand_color(state['fg_color'])
            styles.append(f'color: #{color};')

        if state['bg_color'] and state['bg_color'] != 'inherit':
            color = self._expand_color(state['bg_color'])
            styles.append(f'background-color: #{color};')

        if is_link:
            classes.append('micron-link-text')

        if styles:
            style_str = ' '.join(styles)
            class_str = ' '.join(classes)
            return f'<span class="{class_str}" style="{style_str}">{escaped}</span>'
        else:
            return escaped

    def _expand_color(self, color: str) -> str:
        """Expand 3-digit hex color to 6-digit"""
        if not color or color == 'default' or color == 'inherit':
            return ''
        color = color.lstrip('#')
        if len(color) == 3:
            return ''.join(c + c for c in color)
        elif len(color) == 6:
            return color
        return color


def micron_to_html(markup: str, destination: str = "", path: str = "/",
                   fg_color: Optional[str] = None, bg_color: Optional[str] = None) -> str:
    """
    Convert Micron markup to HTML.

    Args:
        markup: Raw Micron markup text
        destination: Current destination hash (for relative links)
        path: Current page path (for relative links)
        fg_color: Default foreground color
        bg_color: Default background color

    Returns:
        HTML string
    """
    parser = MicronParser(destination, path)
    return parser.parse(markup, fg_color, bg_color)
