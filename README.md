# Patchouli: an interactive patch file splitter

Have you ever committed a big batch of changes that need to be code reviewed?

Did it happen that the code got finetuned and bugfixed over time, but you want
to split up the final change set in a way that makes it easier on the reviewers?

Does it so happen that the preferred review units don't line up with your commit
units? Maybe not even with complete files?

If you've ever wanted to split a patch set into parts at the hunk level, and do
so iteratively and interactively, patchouli is for you!

## Installing

Patchouli is available via pip:

    pip install patchouli

## Usage

(I'll use an arbitrary Linux kernel patch file to demonstrate)

Run `patchouli` on your patch file(s):

    $ patchouli example.patch

Patchouli will show you the first hunk and a prompt to start typing commands.

    (Type 'create foo' then 'move foo' to start classifying hunks)
    **************** linux/arch/i386/kernel/process.c.seg ****************
        * Save away %fs and %gs. No need to save %es and %ds, as
        * those are always kernel segments while inside the kernel.
        */
    -	asm volatile("movl %%fs,%0":"=m" (*(int *)&prev->fs));
    -	asm volatile("movl %%gs,%0":"=m" (*(int *)&prev->gs));
    +	asm volatile("mov %%fs,%0":"=m" (prev->fs));
    +	asm volatile("mov %%gs,%0":"=m" (prev->gs));

        /*
         * Restore %fs and %gs if needed.
    unclassified (1/8)>

Patchouli calls a bunch of hunks a "change set". At the start, all of your hunks
will be in the change set named "unclassified". To see all hunks, type `ls`:

    > ls

You'll see the following:

    ->   1) linux/arch/i386/kernel/process.c.seg
         2) linux/arch/i386/kernel/vm86.c.seg
         3) linux/arch/x86_64/kernel/process.c.seg
         4) linux/arch/x86_64/kernel/process.c.seg
         5) linux/arch/x86_64/kernel/process.c.seg
         6) linux/arch/x86_64/kernel/process.c.seg
         7) linux/include/asm-i386/system.h.seg
         8) linux/include/asm-i386/system.h.seg
    (Type 'hunk N' to go to a specific hunk, 'show' to show the current hunk)

Create a new change set to move changes into:

    > create i386

Start moving the first two hunks into this new change set:

    > move i386   (or simply 'm i386')
    > m           (without a name repeats the last move)
    > <enter>     (simply pressing enter repeats the last command)

Type `set` to see an overview of all change sets:

    > set

       i386 (2 hunks)
    -> unclassified (6 hunks)

Type `write` to write out the changes to individual `.patch` files:

    > write

    Wrote i386.patch
    Wrote unclassified.patch

## Helpful tips

* Type `help` for a list of all commands.
* `undo` undoes the last move.
* You can move through the hunk list by typing `next` and `back`.
* `next`, `back` and `move` can be shortened to `n`, `b` and `m`.
* The shell has tab completion, courtsey of Python's `cmd` library.
