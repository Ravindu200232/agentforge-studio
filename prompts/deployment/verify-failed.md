
## The studio checked your live address itself and it did not hold

You marked the run live, and the studio then called the addresses in your `checks` (and `url`) from its
own side. These did not answer the way you recorded:

{{failures}}

This is the one repair round (`deployment-repair`): read the platform's logs for these requests once, name the
cause, repair the source or the configuration, redeploy once, and run only these checks again. Do not run tests
or the whole check list again. Update `checks` with what you now see. If they still do not hold afterwards, mark
the run `FAILED` with the cause in `error`: there is no further round.
