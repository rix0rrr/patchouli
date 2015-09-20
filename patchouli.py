#!/usr/bin/env python

try:
  import cStringIO as io
except ImportError:
  import io

import cmd
import itertools
import pprint
import string
import traceback
import sys

import termcolor
import unidiff


def list_generator(fn):
  """Make a generator return a list."""
  def decorated(*args, **kwargs):
    return list(fn(*args, **kwargs))
  return decorated


def get_file_id(a):
  return a.file_id


class Hunk(object):
  """A single change hunk (immutable)."""
  def __init__(self, patch_file, patch):
    self.patch_file = patch_file
    self.patch = patch

  @property
  def file_id(self):
    """Return a combination of source and target file to uniquify files."""
    return self.patch_file.source_file + ':' + self.patch_file.target_file

  @property
  def filename(self):
    return self.patch_file.path

  def prn(self):
    termcolor.cprint('{:*^70}'.format(' %s ' % self.filename), 'yellow')
    for line in self.patch:
      if line.is_removed:
        termcolor.cprint('-' + line.value, 'red')
      elif line.is_added:
        termcolor.cprint('+' + line.value, 'green')
      else:
        print(' ' + line.value)

  def write_file_header(self, fobj):
    fobj.write('--- %s\t%s\n' % (self.patch_file.source_file, self.patch_file.source_timestamp))
    fobj.write('+++ %s\t%s\n' % (self.patch_file.target_file, self.patch_file.target_timestamp))

  def write_hunk(self, fobj):
    fobj.write(str(self.patch) + '\n')


@list_generator
def make_hunks(patch_set):
  for patch_file in patch_set:
    for hunk in patch_file:
      yield Hunk(patch_file, hunk)


@list_generator
def group_hunks_by_file(hunks):
  """Return a list of lists of all hunks that belong to the same file."""
  ss = sorted(hunks, key=get_file_id)
  for _, hunks in itertools.groupby(ss, get_file_id):
    yield list(hunks)

class ChangeSet(object):
  """Mutable change set.

  Consists of a collection of hunks and an edit cursor.
  """
  def __init__(self, hunks):
    self.hunks = hunks
    self.index = 1

  def _clip_index(self):
    if self.index > self.count:
      self.index = self.count
    if self.index < 1:
      self.index = 1

  def _not_empty(self):
    self._clip_index()
    if self.index > len(self.hunks):
      raise RuntimeError('This change set is empty')

  @property
  def empty(self):
    return not self.hunks

  @property
  def current_hunk(self):
    self._not_empty()
    return self.hunks[self.index - 1]

  def skip(self):
    if self.index == self.count:
      self.go(1)
    else:
      self.go(self.index + 1)

  def back(self):
    if self.index == 1:
      self.go(self.count)
    else:
      self.go(self.index - 1)

  def go(self, index):
    self.index = index
    self._clip_index()

  def prn(self):
    for i, hunk in enumerate(self.hunks):
      indicator = '->' if  i + 1 == self.index else '  '
      print('%s %3d) %s' % (indicator, i + 1, hunk.filename))

  def take(self):
    """Remove the currently selected hunk."""
    i = self.index - 1
    if not (0 <= i < self.count):
      raise RuntimeError('Change set is empty')
    ret = self.hunks[i]
    self.hunks[i:i+1] = []
    return ret

  def pop(self):
    return self.hunks.pop()

  def put(self, hunk):
    self.hunks.append(hunk)

  def insert(self, index, hunk):
    self.hunks.insert(index - 1, hunk)

  @property
  def count(self):
    return len(self.hunks)

  @property
  def progress(self):
    if self.count:
      return '%d/%d' % (self.index, self.count)
    return 'empty'

  def write(self, fobj):
    """Write this change set to a file-like object."""
    for hunks in group_hunks_by_file(self.hunks):
      hunks[0].write_file_header(fobj)
      for hunk in hunks:
        hunk.write_hunk(fobj)

class UndoPoint(object):
  def __init__(self, index, source_set, target_set):
    self.index = index
    self.source_set = source_set
    self.target_set = target_set


class ChangeCollection(object):
  """Collection of all change sets.

  Has a currently active change set, and serves as a ViewModel of the application.
  """
  def __init__(self, unclassified):
    self.sets = {'unclassified': unclassified}
    self.current_set_name = 'unclassified'
    self.undo_stack = []

  @property
  def set_names(self):
    return sorted(self.sets.keys())

  @property
  def current_set(self):
    return self.sets[self.current_set_name]

  def prn(self):
    for name in self.set_names:
      indicator = '->' if  self.current_set_name == name else '  '
      print('%s %s (%d hunks)' % (indicator, name, self.sets[name].count))

  @property
  def current_hunk(self):
    """Return the next hunk from the current set."""
    return self.current_set.current_hunk

  def skip(self):
    self.current_set.skip()

  def back(self):
    self.current_set.back()

  def select(self, name):
    if name not in self.sets:
      raise RuntimeError('No such set: %r' % name)
    self.current_set_name = name

  def create(self, name):
    if name in self.sets:
      raise RuntimeError('Set %r already exists' % name)
    self.sets[name] = ChangeSet([])

  def move(self, name):
    if name == self.current_set_name:
      raise RuntimeError('Hunk is already in change set %r' % name)
    if name not in self.sets:
      raise RuntimeError('No such change set: %r (Type \'create %s\' to create it first)' % (name, name))
    hunk = self.current_set.take()
    self.sets[name].put(hunk)

    self.undo_stack.append(UndoPoint(self.current_set.index, self.current_set_name, name))

  def undo(self):
    if not self.undo_stack:
      raise RuntimeError('Nothing to undo')
    undo = self.undo_stack.pop()

    hunk = self.sets[undo.target_set].pop()  # Always remove from the last position
    self.sets[undo.source_set].insert(undo.index, hunk)  # Insert at source loc

    # Move to this hunk
    self.current_set_name = undo.source_set
    self.current_set.go(undo.index)

    return undo

  def write_set(self, name):
    if name not in self.sets:
      raise RuntimeError('No such set: %r' % name)
    filename = name + '.patch'
    with open(filename, 'w') as f:
      self.sets[name].write(f)
    print('Wrote %s' % filename)

  def autocomplete(self, prefix):
    return [name for name in self.set_names if name.startswith(prefix)]


class CommandLoop(cmd.Cmd):
  """User interface for the application."""
  def __init__(self, coll):
    cmd.Cmd.__init__(self)
    self.coll = coll
    self.update_prompt()
    self.cmdqueue.append('show')
    self.last_move = ''

  def onecmd(self, str):
    try:
      return cmd.Cmd.onecmd(self, str)
    except RuntimeError as e:
      termcolor.cprint(e, 'red')
    except Exception as e:
      termcolor.cprint(traceback.format_exc(), 'red')

  def show_current_hunk(self):
    self.update_prompt()
    self.coll.current_hunk.prn()

  def update_prompt(self):
    self.prompt = '%s (%s)> ' % (self.coll.current_set_name, self.coll.current_set.progress)

  def do_set(self, line):
    """set [NAME]

    List all change sets, or switch to a different change set.
    """
    if line:
      self.coll.select(line)
      self.update_prompt()
    else:
      self.coll.prn()

  def do_create(self, line):
    """create NAME

    Create a new change set."""
    if not line:
      raise RuntimeError('Create needs an argument')
    self.coll.create(line)
    print('(Change set created. Type \'set %s\' to switch to it, or \'move %s\' to move a hunk there)' % (line, line))

  def do_show(self, line):
    """show

    Show current hunk again."""
    self.show_current_hunk()

  def do_ls(self, line):
    """ls

    List the current change set."""
    self.coll.current_set.prn()
    if not self.coll.current_set.empty:
      print('(Type \'hunk N\' to go to a specific hunk, \'show\' to show the current hunk)')

  def do_n(self, line):
    """next | n

    Skip this hunk, go to the next one."""
    self.do_next(line)

  def do_next(self, line):
    """next | n

    Skip this hunk, go to the next one."""
    self.coll.skip()
    self.show_current_hunk()

  def do_b(self, line):
    """back | b

    Go back to the previous hunk.
    """
    self.do_back(line)

  def do_back(self, line):
    """back | b

    Go back to the previous hunk.
    """
    self.coll.back()
    self.show_current_hunk()

  def do_hunk(self, num):
    """hunk INDEX

    Go to a specific hunk #.
    """
    i = int(num)
    self.coll.current_set.go(i)
    self.show_current_hunk()

  def do_move(self, name):
    """move [NAME] | m [NAME]

    Move the current hunk to a different change set. If no name is given, the argument of the most
    recent move command is reused.
    """
    if not name:
      name = self.last_move

    if not name:
      raise RuntimeError('move needs a change set name on the first invocation')
    self.last_move = name
    self.coll.move(name)
    print('(Hunk moved to change set %r)' % name)
    self.show_current_hunk()

  def complete_set(self, text, line, beginidx, endidx):
    return self.coll.autocomplete(text)

  complete_m = complete_set
  complete_move = complete_set
  complete_write = complete_set

  def do_m(self, name):
    """move NAME | m NAME

    Move the current hunk to a different change set.
    """
    self.do_move(name)

  def do_undo(self, line):
    """undo

    Undo the last 'move' command.
    """
    undo = self.coll.undo()
    print('(Moved hunk back from %r to %r)' % (undo.target_set, undo.source_set))
    self.show_current_hunk()

  def do_write(self, line):
    """write [SET]

    Write a single set, or write all sets, to a patch file with the same name.
    """
    if line:
      self.coll.write_set(line)
    else:
      for name in self.coll.set_names:
        self.coll.write_set(name)

  def do_EOF(self, line):
    """Exit."""
    return True


def read_all_files(filenames):
  """Read all files into a StringIO buffer."""
  return io.StringIO('\n'.join(open(f).read() for f in filenames))


def main():
  filenames = sys.argv[1:]
  if not filenames:
    print('Usage: patchouli.py FILE [...]')
    sys.exit(1)

  buffer = read_all_files(filenames)
  patch_set = unidiff.PatchSet(buffer)
  unclassified = ChangeSet(make_hunks(patch_set))
  app = ChangeCollection(unclassified)
  print('(Type \'create foo\' then \'move foo\' to start classifying hunks)')
  try:
    CommandLoop(app).cmdloop()
  except KeyboardInterrupt:
    sys.exit(1)


if __name__ == '__main__':
  main()
