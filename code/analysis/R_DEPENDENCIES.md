# R dependencies

Analysis scripts in this directory target **R 4.3.2** with the following packages. Versions are the ones used to produce the CSVs in `4_analyze/output/`.

| Package | Version | Used for |
| --- | --- | --- |
| `dplyr`    | 1.1.4  | data manipulation throughout `results_pipeline.R` |
| `tidyr`    | 1.3.x  | reshaping per-cell counts |
| `readr`    | 2.1.x  | CSV I/O |
| `purrr`    | 1.0.x  | functional helpers |
| `lme4`     | 1.1.37 | `glmer()` for the per-model binomial GLMM (§4.5) |
| `emmeans`  | 1.11.1 | planned contrasts from the GLMMs |
| `ggplot2`  | 3.5.x  | figure rendering |
| `scales`   | 1.3.x  | axis formatting |
| `stringr`  | 1.5.x  | model-slug parsing |
| `jsonlite` | 1.8.x  | reading per-cell JSONL inputs |

Install (CRAN):

```r
install.packages(c("dplyr", "tidyr", "readr", "purrr",
                   "lme4", "emmeans", "ggplot2",
                   "scales", "stringr", "jsonlite"))
```

For exact-version reproducibility, initialise an `renv` project and `renv::snapshot()` after installing the above. The headline numbers (Table 2, Table 3, Table 4) are produced by `Rscript results_pipeline.R`; the `SUBSTANTIVE` log-odds threshold is set to **0.36** at the top of the script (§4.5 of the thesis).
