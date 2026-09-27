
## The studio checked your live address itself and it did not hold

You marked the run live, and the studio then called the addresses in your `checks` (and `url`) from its
own side. These did not answer the way you recorded:

{{failures}}

Treat this as a bug found in the deployed application. Follow `deployment-repair`: read the platform's
logs for the requests, name the cause, repair the source or the configuration, redeploy, and prove every
check again from the start. Update `checks` with what you now see. Do not mark the run live until they
all hold.
