#!/usr/bin/env Rscript
# Synthetic checks for the slope tests in scripts/mn_squeeze/core_city_models.R.
# Only the function definitions are loaded, so no study data is read.
# Run from the project root: Rscript tests/test_core_city_models.R

suppressPackageStartupMessages({
  library(lmtest)
  library(sandwich)
  library(here)
})

exprs <- parse(here::here("scripts/mn_squeeze/core_city_models.R"))
is_definition <- vapply(exprs, function(e) {
  grepl("^combination_p <- function", deparse(e)[1])
}, logical(1))
stopifnot(sum(is_definition) == 1L)
eval(exprs[[which(is_definition)]], globalenv())

set.seed(42)
n <- 400
d <- data.frame(x = rnorm(n), g = factor(rep(c("a", "b"), each = n / 2)))
d$y <- 1 - 0.5 * d$x + 0.2 * (d$g == "b") * d$x + rnorm(n)
m <- lm(y ~ x * g, data = d)
vc <- vcovHC(m, type = "HC1")

# A single term reproduces the coeftest p-value under a normal reference.
single <- coeftest(m, vcov = vc, df = Inf)["x", 4]
stopifnot(abs(combination_p(m, "x", vc) - single) < 1e-12)

# A sum of terms uses the full covariance, including the cross term.
w <- c(0, 1, 0, 1)
se <- sqrt(drop(t(w) %*% vc %*% w))
expected <- 2 * pnorm(-abs(sum(w * coef(m)) / se))
stopifnot(abs(combination_p(m, c("x", "x:gb"), vc) - expected) < 1e-12)

# A coefficient sum near zero is not significant; a large one is.
d$y2 <- 1 + 0.5 * d$x - 0.5 * (d$g == "b") * d$x + rnorm(n)
m2 <- lm(y2 ~ x * g, data = d)
stopifnot(combination_p(m2, c("x", "x:gb"), vcovHC(m2, type = "HC1")) > 0.01,
          combination_p(m, "x", vc) < 1e-6)

# Unknown terms fail loudly instead of testing an empty combination.
stopifnot(inherits(try(combination_p(m, "missing", vc), silent = TRUE), "try-error"))

cat("Core-city slope test checks passed.\n")
