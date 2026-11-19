# First steps with dsoxlab

This lab is not about Linux, Terraform or Ansible. **Its subject is dsoxlab
itself**: the loop you will repeat on every other lab, whatever the catalog.

## The loop

A lab always goes through the same five moves.

| Move | What it does |
|---|---|
| `dsoxlab run <id>` | Prepares the lab and drops you in its work directory |
| `dsoxlab course <id>` | Shows the lesson, this very page |
| `dsoxlab challenge <id>` | Shows the mission: what you have to produce |
| `dsoxlab hint <id>` | Reveals one more hint, at a cost on your score |
| `dsoxlab check <id>` | Runs the tests and records the score |

Two of them deserve a comment.

**`check` reads the state you produced, never the commands you typed.** There is
no history to please and no exact wording to guess: the tests look at the files.
That is why you can reach the answer any way you like.

**`hint` costs points, and says so before spending them.** It is not a
punishment: a hint used deliberately is cheaper than an hour lost. `dsoxlab
scores` shows what a lab finally earned.

## Where you work

`dsoxlab run` places you in the lab's work directory. Everything you create
there is what gets validated. Nothing else on your machine is touched.

## The word of the lesson

The mission below asks you for a word that appears here, and only here. It is:

    catalogue

Now read the mission: `dsoxlab challenge premiers-pas`.
