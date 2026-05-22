#!/usr/bin/env Rscript
# Reproducible Results-section pipeline.
#
# Reads per-model judged results, fits per-model logistic mixed-effects models
# of `deceived ~ wording * split + (1 | item_id)`, extracts the three planned
# emmeans contrasts (Sub-RQ1 wording, Sub-RQ2 split, Sub-RQ3 interaction), and
# writes both CSV outputs and final figures for the Results section.
#
# Run from the repo root:
#   Rscript code/analysis/results_pipeline.R
#
# Inputs:
#   3_judge/output/<model_slug>/results.csv     for each thesis target model
#   2_generate/output/qwen__qwen3.5-9b/gen_*.jsonl  (looping-failure stats)
#
# Outputs (4_analyze/output/):
#   glmm_contrasts.csv           per-model x per-contrast estimates + Wald CIs
#   glmm_contrast_summary.csv    per-contrast distribution-of-effects summary
#   cell_deception_rates.csv     model x framing rates with 95% Wilson CIs
#   glmm_diagnostics.csv         per-model fit diagnostics (singularity, item-SD)
#   successor_pairs_long.csv     within-lineage original vs new generation
#   qwen35_response_subset.csv   qwen3.5-9b dual statistic (all vs response-cells)
#   qwen35_loop_summary.csv      qwen3.5-9b empty-response rate by framing
#   qwen35_responder_rates_by_framing.csv  qwen3.5-9b deception rate on responding cells
#
# Figures: only fig_results_per_model_bars (Figure 6) and fig_results_forest
# (Figure 5) are produced; both written to a `figures/` directory if the
# REPO_FIGURES environment variable is set, otherwise skipped. The supplementary
# materials repository does not ship the report sources, so figure rendering is
# off by default.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(purrr)
  library(lme4)
  library(emmeans)
  library(ggplot2)
  library(scales)
  library(stringr)
})

# Defense-in-depth: pipeline currently contains no stochastic step (bobyqa,
# Wilson CIs, and emmeans contrasts are deterministic), but a seed is set in
# case future steps (e.g. bootstrap CIs) introduce randomness.
set.seed(20260428)

REPO <- Sys.getenv("REPO_ROOT", getwd())
if (basename(REPO) == "analysis") REPO <- dirname(dirname(REPO))
JUDGE_OUT <- file.path(REPO, "3_judge", "output")
GEN_OUT <- file.path(REPO, "2_generate", "output")
OUT_CSV <- file.path(REPO, "4_analyze", "output")
OUT_FIG <- Sys.getenv("REPO_FIGURES", "")  # empty = skip figure rendering
dir.create(OUT_CSV, showWarnings = FALSE, recursive = TRUE)
if (nzchar(OUT_FIG)) dir.create(OUT_FIG, showWarnings = FALSE, recursive = TRUE)

# ----------------------------------------------------------------------------
# Target-model registry
# ----------------------------------------------------------------------------
THESIS_MODELS <- tribble(
  ~slug,                                ~short,         ~display,           ~vendor,    ~generation,
  "openai__gpt-4o-2024-08-06",          "gpt-4o",       "GPT-4o",           "OpenAI",   "original",
  "openai__gpt-5.4",                    "gpt-5.4",      "GPT-5.4",          "OpenAI",   "new",
  "google__gemini-2.0-flash-001",       "gemini-2",     "Gemini-2-Flash",   "Google",   "original",
  "google__gemini-3-flash-preview",     "gemini-3",     "Gemini-3-Flash",   "Google",   "new",
  "deepseek__deepseek-r1",              "r1",           "DeepSeek-R1",      "DeepSeek", "original",
  "deepseek-ai__DeepSeek-V3.2",         "V3.2",         "DeepSeek-V3.2",    "DeepSeek", "new",
  "qwen__qwen-2.5-7b-instruct",         "qwen2.5-7b",   "Qwen2.5-7B",       "Qwen",     "original",
  "qwen__qwen3.5-9b",                   "qwen3.5-9b",   "Qwen3.5-9B",       "Qwen",     "new",
)

# Display order: original then new within each vendor (paired generations adjacent).
DISPLAY_ORDER <- THESIS_MODELS$display
THESIS_MODELS <- THESIS_MODELS |>
  mutate(display = factor(display, levels = DISPLAY_ORDER))

# ----------------------------------------------------------------------------
# Load and code data
# ----------------------------------------------------------------------------
load_model <- function(slug) {
  path <- file.path(JUDGE_OUT, slug, "results.csv")
  d <- read_csv(path, show_col_types = FALSE,
                col_types = cols(.default = col_character(),
                                 scenario_id = col_integer(),
                                 deceived = col_integer()))
  d |>
    filter(response %in% c("decept", "honest")) |>
    mutate(
      slug = slug,
      item_id = paste(scenario_id, condition, sep = "_"),
      wording = if_else(framing %in% c("A", "B"), "narrated", "interactive"),
      split = if_else(framing %in% c("A", "C"), "single", "split"),
      wording = factor(wording, levels = c("narrated", "interactive")),
      split = factor(split, levels = c("single", "split")),
      framing = factor(framing, levels = c("A", "B", "C", "D")),
      deceived = as.integer(deceived)
    ) |>
    select(slug, scenario_id, item_id, framing, condition, wording, split,
           thought, response, deceived)
}

cat("Loading data...\n")
all_data <- THESIS_MODELS$slug |>
  set_names() |>
  map(load_model) |>
  list_rbind() |>
  left_join(THESIS_MODELS, by = "slug")

stopifnot(all(table(all_data$slug) == 1632))
cat("Loaded ", nrow(all_data), " rows across ",
    length(unique(all_data$slug)), " models.\n", sep = "")

# ----------------------------------------------------------------------------
# 1. Cell deception rates (model x framing) with Wilson 95% CIs
# ----------------------------------------------------------------------------
wilson <- function(k, n, conf = 0.95) {
  # Two-sided Wilson CI for a proportion.
  z <- qnorm(1 - (1 - conf) / 2)
  p <- k / n
  d <- 1 + z^2 / n
  c <- p + z^2 / (2 * n)
  s <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2))
  list(lo = (c - s) / d, hi = (c + s) / d)
}

cell_rates <- all_data |>
  group_by(slug, short, display, vendor, generation, framing) |>
  summarise(n_decept = sum(deceived), n = n(), .groups = "drop") |>
  mutate(
    rate = n_decept / n,
    ci_lo = wilson(n_decept, n)$lo,
    ci_hi = wilson(n_decept, n)$hi
  )

write_csv(cell_rates, file.path(OUT_CSV, "cell_deception_rates.csv"))

# ----------------------------------------------------------------------------
# 2. Per-model GLMM fits and three planned contrasts via emmeans
# ----------------------------------------------------------------------------
# Contrast weights on the four-cell A,B,C,D factorial. All three contrasts are
# scaled to a unit-difference interpretation on the log-odds scale, so that
# the wording, split, and interaction estimates are directly comparable to
# one another and to the +-0.36 substantive threshold. The actual numeric
# weights are applied inline below in fit_one_model() in emmeans grid order
# (A, C, B, D), which differs from the natural (A, B, C, D) ordering.


# Fit `deceived ~ wording * split + (1 + wording * split | item_id)` per model
# (Barr et al., 2013 maximal random-effect structure for the within-item
# factors), with fallbacks to a zero-correlation structure (`||`) and then to
# intercept-only if the maximal model fails to converge.
fit_one_model <- function(d_model) {
  d_model <- d_model |>
    mutate(framing = factor(framing, levels = c("A", "B", "C", "D")),
           wording = factor(wording, levels = c("narrated", "interactive")),
           split   = factor(split,   levels = c("single", "split")))
  fit <- glmer(
    deceived ~ wording * split + (1 | item_id),
    family = binomial(),
    data = d_model,
    control = glmerControl(optimizer = "bobyqa",
                           optCtrl = list(maxfun = 2e5))
  )

  # emmeans grid order for `~ wording * split` with the factor levels set above
  # is (narrated, single), (interactive, single), (narrated, split),
  # (interactive, split) = (A, C, B, D). Apply contrasts as numeric weights in
  # that order:
  contrast_weights <- list(
    wording     = c(-0.5,  0.5, -0.5,  0.5),  # C+D vs A+B  i.e. weights at (A, C, B, D)
    split       = c(-0.5, -0.5,  0.5,  0.5),  # B+D vs A+C
    interaction = c( 0.5, -0.5, -0.5,  0.5)   # (D-C)-(B-A) / 2
  )
  emm_lo <- emmeans(fit, ~ wording * split)
  est_lo <- contrast(emm_lo, method = contrast_weights) |>
    summary(infer = c(TRUE, FALSE), level = 0.95) |>
    as_tibble() |>
    rename(rq = contrast)
  # Rate-scale contrasts directly on empirical cell rates (item-marginal),
  # not GLMM-predicted conditional rates (the latter are conditional on
  # item random effect = 0 and underestimate marginal rates when item RE
  # variance is large). Each contrast is a linear combination of the four
  # cell rates; per-cell observations are independent across items, so the
  # contrast variance is sum(w_i^2 * p_i * (1 - p_i) / n_i) and Wald CIs
  # follow from the normal approximation.
  cell_props <- d_model |>
    group_by(framing) |>
    summarise(p = mean(deceived), n = n(), .groups = "drop")
  # Reorder to (A, C, B, D) emmeans-grid order:
  cell_idx <- c("A" = 1, "C" = 2, "B" = 3, "D" = 4)
  p_vec <- cell_props$p[match(names(cell_idx), cell_props$framing)]
  n_vec <- cell_props$n[match(names(cell_idx), cell_props$framing)]
  est_pr <- tibble(
    rq = names(contrast_weights),
    delta_p = vapply(contrast_weights, function(w) sum(w * p_vec), 0),
    delta_p_se = vapply(contrast_weights,
                        function(w) sqrt(sum(w^2 * p_vec * (1 - p_vec) / n_vec)), 0)
  ) |>
    mutate(delta_p_lo = delta_p - qnorm(0.975) * delta_p_se,
           delta_p_hi = delta_p + qnorm(0.975) * delta_p_se)
  est <- est_lo |>
    left_join(est_pr |> select(rq, delta_p, delta_p_lo, delta_p_hi), by = "rq")

  cell_min_decept <- d_model |>
    group_by(framing) |>
    summarise(n_dec = sum(deceived), .groups = "drop") |>
    pull(n_dec) |>
    min()
  conv_msgs <- fit@optinfo$conv$lme4$messages
  conv_msg <- if (length(conv_msgs) == 0) "" else paste(conv_msgs, collapse = "; ")
  vc <- as.data.frame(VarCorr(fit))
  item_intercept_sd <- vc$sdcor[vc$grp == "item_id" & vc$var1 == "(Intercept)" & is.na(vc$var2)]
  if (length(item_intercept_sd) == 0) item_intercept_sd <- NA_real_
  diagnostics <- tibble(
    n_decept_min_cell = cell_min_decept,
    is_singular = isSingular(fit),
    conv_message = conv_msg,
    item_intercept_sd = item_intercept_sd
  )

  list(fit = fit, est = est, diagnostics = diagnostics)
}

cat("Fitting per-model GLMMs...\n")
fits <- list()
contrasts_rows <- list()
diagnostics_rows <- list()
for (s in THESIS_MODELS$slug) {
  cat("  ", s, "\n", sep = "")
  d_m <- all_data |> filter(slug == s)
  res <- fit_one_model(d_m)
  fits[[s]] <- res$fit
  meta <- THESIS_MODELS |> filter(slug == s)
  contrasts_rows[[s]] <- res$est |>
    mutate(slug = s, short = meta$short, display = meta$display,
           vendor = meta$vendor, generation = meta$generation, .before = 1)
  diagnostics_rows[[s]] <- res$diagnostics |>
    mutate(slug = s, short = meta$short, display = meta$display, .before = 1)
}

diagnostics_df <- list_rbind(diagnostics_rows)
write_csv(diagnostics_df, file.path(OUT_CSV, "glmm_diagnostics.csv"))
cat("\nGLMM fit diagnostics:\n")
print(diagnostics_df, n = Inf)

contrast_df <- list_rbind(contrasts_rows) |>
  rename(log_odds = estimate,
         ci_lo = asymp.LCL, ci_hi = asymp.UCL,
         se = SE) |>
  left_join(diagnostics_df |> select(slug, n_decept_min_cell,
                                     is_singular, item_intercept_sd),
            by = "slug") |>
  mutate(
    rq_label = recode(rq,
      wording = "Sub-RQ1: wording (interactive vs narrated)",
      split = "Sub-RQ2: delivery split (split vs single)",
      interaction = "Sub-RQ3: wording x split interaction"
    ),
    odds_ratio = exp(log_odds),
    or_lo = exp(ci_lo),
    or_hi = exp(ci_hi),
    # rate-scale contrasts in percentage points
    delta_pp    = 100 * delta_p,
    delta_pp_lo = 100 * delta_p_lo,
    delta_pp_hi = 100 * delta_p_hi
  ) |>
  select(slug, short, display, vendor, generation,
         rq, rq_label, log_odds, se, ci_lo, ci_hi,
         odds_ratio, or_lo, or_hi,
         delta_pp, delta_pp_lo, delta_pp_hi,
         n_decept_min_cell, is_singular, item_intercept_sd)

write_csv(contrast_df, file.path(OUT_CSV, "glmm_contrasts.csv"))

# ----------------------------------------------------------------------------
# 3. Distribution-of-effects summary per RQ
# ----------------------------------------------------------------------------
SUBSTANTIVE <- 0.36  # log-odds substantive threshold from Methods (Cohen-small d=0.2 via Chinn 2000 conversion)

contrast_summary <- contrast_df |>
  group_by(rq, rq_label) |>
  summarise(
    n_models = n(),
    median = median(log_odds),
    min = min(log_odds), max = max(log_odds),
    n_ci_excl_zero = sum(ci_lo > 0 | ci_hi < 0),
    n_above_substantive = sum(abs(log_odds) >= SUBSTANTIVE),
    n_pos_substantive = sum(log_odds >= SUBSTANTIVE),
    n_neg_substantive = sum(log_odds <= -SUBSTANTIVE),
    n_pos_direction = sum(log_odds > 0),
    .groups = "drop"
  )

write_csv(contrast_summary, file.path(OUT_CSV, "glmm_contrast_summary.csv"))

# ----------------------------------------------------------------------------
# 4. Within-lineage successor comparison (per vendor x framing)
# ----------------------------------------------------------------------------
successor_long <- cell_rates |>
  select(short, display, vendor, generation, framing, n, n_decept, rate) |>
  pivot_wider(id_cols = c(vendor, framing),
              names_from = generation,
              values_from = c(rate, n, n_decept, short),
              names_glue = "{generation}_{.value}") |>
  mutate(delta = new_rate - original_rate)

write_csv(successor_long, file.path(OUT_CSV, "successor_pairs_long.csv"))

# ----------------------------------------------------------------------------
# 6. Qwen3.5-9B looping: rate over all cells vs response-only cells
# ----------------------------------------------------------------------------
`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a
suppressPackageStartupMessages(library(jsonlite))

qwen_files <- file.path(GEN_OUT, "qwen__qwen3.5-9b",
                        paste0("gen_", c("A", "B", "C", "D"), ".jsonl"))
qwen_gen <- map_dfr(qwen_files, function(p) {
  fr <- str_extract(basename(p), "(?<=gen_)[ABCD]")
  con <- file(p, "r")
  on.exit(close(con))
  out <- list()
  i <- 0
  while (length(line <- readLines(con, n = 1, warn = FALSE)) > 0) {
    j <- jsonlite::fromJSON(line, simplifyVector = TRUE)
    i <- i + 1
    out[[i]] <- tibble(
      framing = fr,
      scenario_id = j$scenario_id,
      condition = j$condition,
      cleaned_response = j$cleaned_response %||% "",
      completion_tokens = j$completion_tokens %||% NA_integer_
    )
  }
  list_rbind(out)
})

qwen_summary <- qwen_gen |>
  mutate(empty = cleaned_response == "" | is.na(cleaned_response)) |>
  group_by(framing) |>
  summarise(
    n = n(),
    n_empty = sum(empty),
    rate_empty = n_empty / n,
    n_cap_hit = sum(completion_tokens >= 16000, na.rm = TRUE)
  )

# Deception rate over all cells vs response-only cells (joining judge labels)
qwen_judged <- all_data |> filter(slug == "qwen__qwen3.5-9b") |>
  mutate(scenario_id = as.integer(scenario_id))
qwen_join <- qwen_judged |>
  left_join(qwen_gen |> mutate(framing = factor(framing, levels = c("A","B","C","D"))),
            by = c("scenario_id", "condition", "framing"))

qwen_dual <- qwen_join |>
  mutate(empty = cleaned_response == "" | is.na(cleaned_response)) |>
  summarise(
    rate_all = mean(deceived),
    rate_response_cells = mean(deceived[!empty]),
    n_total = n(),
    n_empty = sum(empty),
    rate_empty_cells = n_empty / n_total
  )

qwen_overall <- qwen_summary |>
  summarise(n = sum(n), n_empty = sum(n_empty), rate_empty = n_empty / n,
            n_cap_hit = sum(n_cap_hit)) |>
  mutate(framing = "ALL", .before = 1)

qwen_out <- bind_rows(qwen_summary, qwen_overall)
write_csv(qwen_out, file.path(OUT_CSV, "qwen35_loop_summary.csv"))
write_csv(qwen_dual, file.path(OUT_CSV, "qwen35_response_subset.csv"))

# Per-framing responder-only rates with Wilson CIs, used as the gray overlay
# on the Qwen3.5-9B panel of the per-model bars figure.
qwen35_responder_rates <- qwen_join |>
  mutate(empty = cleaned_response == "" | is.na(cleaned_response)) |>
  filter(!empty) |>
  group_by(framing) |>
  summarise(n_decept = sum(deceived), n = n(), .groups = "drop") |>
  mutate(
    rate = n_decept / n,
    ci_lo = wilson(n_decept, n)$lo,
    ci_hi = wilson(n_decept, n)$hi,
    display = factor("Qwen3.5-9B", levels = DISPLAY_ORDER),
    framing = factor(framing, levels = c("A", "B", "C", "D"))
  )
write_csv(qwen35_responder_rates,
          file.path(OUT_CSV, "qwen35_responder_rates_by_framing.csv"))

# Dual GLMM: all-cells vs response-only contrasts for Qwen3.5-9B (§5.3 of the
# thesis). Refits the same `deceived ~ wording * split + (1 | item_id)` model
# on the responder-only subsample and reports log-odds contrasts side-by-side
# with the all-cells fit produced by fit_one_model() in the main loop.
qwen_glmm_contrasts <- function(d_model) {
  d_model <- d_model |>
    mutate(framing = factor(framing, levels = c("A", "B", "C", "D")),
           wording = factor(wording, levels = c("narrated", "interactive")),
           split   = factor(split,   levels = c("single", "split")))
  fit <- glmer(
    deceived ~ wording * split + (1 | item_id),
    family = binomial(),
    data = d_model,
    control = glmerControl(optimizer = "bobyqa",
                           optCtrl = list(maxfun = 2e5))
  )
  contrast_weights <- list(
    wording     = c(-0.5,  0.5, -0.5,  0.5),
    split       = c(-0.5, -0.5,  0.5,  0.5),
    interaction = c( 0.5, -0.5, -0.5,  0.5)
  )
  emm_lo <- emmeans(fit, ~ wording * split)
  contrast(emm_lo, method = contrast_weights) |>
    summary(infer = c(TRUE, FALSE), level = 0.95) |>
    as_tibble() |>
    rename(rq = contrast)
}

qwen_all <- all_data |> filter(slug == "qwen__qwen3.5-9b") |>
  mutate(scenario_id = as.integer(scenario_id)) |>
  left_join(qwen_gen |> mutate(framing = factor(framing,
                                                levels = c("A","B","C","D"))),
            by = c("scenario_id", "condition", "framing")) |>
  mutate(empty = cleaned_response == "" | is.na(cleaned_response))

qwen_dual_glmm <- bind_rows(
  qwen_glmm_contrasts(qwen_all) |> mutate(subset = "all_cells", .before = 1),
  qwen_glmm_contrasts(qwen_all |> filter(!empty)) |>
    mutate(subset = "response_only", .before = 1)
) |>
  transmute(subset,
            contrast = rq,
            estimate,
            SE,
            df,
            asymp.LCL,
            asymp.UCL)

write_csv(qwen_dual_glmm, file.path(OUT_CSV, "qwen35_glmm_dual.csv"))

# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------
theme_thesis <- function(base_size = 9) {
  theme_minimal(base_size = base_size) +
    theme(
      panel.grid.minor = element_blank(),
      panel.grid.major.y = element_line(color = "grey90", linewidth = 0.3),
      panel.grid.major.x = element_line(color = "grey90", linewidth = 0.3),
      strip.text = element_text(face = "bold", size = base_size),
      legend.position = "bottom",
      legend.title = element_text(size = base_size - 1),
      legend.text = element_text(size = base_size - 1),
      axis.title = element_text(size = base_size),
      plot.caption = element_text(size = base_size - 1, color = "grey40", hjust = 0)
    )
}

save_fig <- function(p, name, width, height) {
  # Figure rendering is skipped unless REPO_FIGURES env var is set (the
  # supplementary materials repository does not ship the report sources).
  if (!nzchar(OUT_FIG)) return(invisible(p))
  ggsave(file.path(OUT_FIG, paste0(name, ".pdf")), p,
         width = width, height = height)
  ggsave(file.path(OUT_FIG, paste0(name, ".png")), p,
         width = width, height = height, dpi = 220)
  invisible(p)
}

per_model_df <- cell_rates |>
  mutate(
    wording = factor(if_else(framing %in% c("A", "B"), "narrated", "interactive"),
                     levels = c("narrated", "interactive")),
    delivery = factor(if_else(framing %in% c("A", "C"), "single", "split"),
                      levels = c("single", "split")),
    display = factor(display, levels = DISPLAY_ORDER)
  )

# --- Figure: per-model bar chart (deception rate by framing, 8 panels) -----
#     One panel per target model. Within each panel: x = framing (A/B/C/D),
#     y = deception rate, one bar per framing with Wilson 95% CIs.
fig_per_model_bars <- ggplot(per_model_df,
                             aes(x = framing, y = rate, fill = framing)) +
  # Background overlay: responder-only rate for Qwen3.5-9B (excludes ~40% of
  # cells that returned no parseable response under the looping pathology).
  # Drawn first so the colored all-cells bar sits in front; the gray extension
  # above the colored bar's top is what reads as the responder-only rate.
  geom_col(data = qwen35_responder_rates,
           aes(x = framing, y = rate),
           inherit.aes = FALSE,
           width = 0.75, fill = "grey78", color = "grey55",
           linewidth = 0.2) +
  geom_col(width = 0.75, color = "grey30", linewidth = 0.2) +
  geom_errorbar(aes(ymin = ci_lo, ymax = ci_hi),
                width = 0.25, color = "grey25", linewidth = 0.35) +
  facet_wrap(~ display, nrow = 2, dir = "v") +
  scale_y_continuous(labels = label_percent(accuracy = 1),
                     limits = c(0, NA), expand = expansion(mult = c(0, 0.10))) +
  scale_fill_manual(values = c(A = "#bccdd6", B = "#7BA7BC",
                               C = "#e0a8a4", D = "#C25450"),
                    guide = "none") +
  labs(x = "Framing", y = "Deception rate") +
  theme_thesis()

save_fig(fig_per_model_bars, "fig_results_per_model_bars",
         width = 7.0, height = 4.4)

# --- Table: per-model cell rates for the appendix (LaTeX, booktabs) --------
#     Tabular twin of the heat map above. One row per model in DISPLAY_ORDER,
#     four rate columns (A, B, C, D) shown as integer percentages.
#     Qwen3.5-9B cells additionally show the responder-only rate in parens.
qwen35_resp_lookup <- qwen35_responder_rates |>
  transmute(framing = as.character(framing), resp_pct = 100 * rate)

rate_tab <- cell_rates |>
  mutate(display = factor(display, levels = DISPLAY_ORDER),
         framing = as.character(framing)) |>
  left_join(qwen35_resp_lookup, by = "framing") |>
  mutate(pct = if_else(
    display == "Qwen3.5-9B",
    sprintf("%.1f\\%% (%.1f\\%%)", 100 * rate, resp_pct),
    sprintf("%.1f\\%%", 100 * rate)
  )) |>
  select(display, framing, pct) |>
  pivot_wider(names_from = framing, values_from = pct) |>
  arrange(display)

rate_tex <- c(
  "% Auto-generated by analysis/results_pipeline.R. Do not hand-edit.",
  "\\begin{tabular}{lcccc}",
  "\\toprule",
  "Model & A & B & C & D \\\\",
  "\\midrule"
)
for (i in seq_len(nrow(rate_tab))) {
  rate_tex <- c(
    rate_tex,
    sprintf("%s & %s & %s & %s & %s \\\\",
            rate_tab$display[i], rate_tab$A[i], rate_tab$B[i],
            rate_tab$C[i], rate_tab$D[i])
  )
}
rate_tex <- c(rate_tex, "\\bottomrule", "\\end{tabular}")

# LaTeX table outputs are gated behind the same env var as figures: they are
# part of the thesis report build, not part of the supplementary-materials repo.
if (nzchar(OUT_FIG)) {
  APPENDIX_ART <- file.path(REPO, "report", "appendix_artifacts")
  dir.create(APPENDIX_ART, showWarnings = FALSE, recursive = TRUE)
  writeLines(rate_tex, file.path(APPENDIX_ART, "cell_rate_table.tex"))
}

# --- Figure: forest plot, three planned contrasts per model ----------------
forest_df <- contrast_df |>
  mutate(display = factor(display, levels = rev(DISPLAY_ORDER)),
         rq_label = factor(rq_label, levels = c(
           "Sub-RQ1: wording (interactive vs narrated)",
           "Sub-RQ2: delivery split (split vs single)",
           "Sub-RQ3: wording x split interaction"
         )))

fig_forest <- ggplot(forest_df, aes(x = log_odds, y = display)) +
  geom_vline(xintercept = 0, linetype = "solid", color = "grey40", linewidth = 0.4) +
  geom_vline(xintercept = c(-SUBSTANTIVE, SUBSTANTIVE),
             linetype = "dotted", color = "grey60", linewidth = 0.4) +
  geom_errorbarh(aes(xmin = ci_lo, xmax = ci_hi), height = 0.25, color = "#0b3954",
                 linewidth = 0.5) +
  geom_point(size = 2.0, color = "#0b3954") +
  facet_wrap(~ rq_label, ncol = 1) +
  labs(x = "Estimated log-odds difference (95% Wald CI)",
       y = NULL) +
  theme_thesis(base_size = 10) +
  theme(panel.spacing = unit(0.9, "lines"),
        strip.text = element_text(face = "bold", hjust = 0))

save_fig(fig_forest, "fig_results_forest", width = 6.4, height = 8.4)

# ----------------------------------------------------------------------------
# 7. Per-model contrast table for the appendix (LaTeX, booktabs)
# ----------------------------------------------------------------------------
fmt_estci <- function(b, lo, hi) {
  sprintf("$%+.2f$ [$%+.2f$, $%+.2f$]", b, lo, hi)
}
fmt_pp <- function(d, lo, hi) {
  sprintf("$%+.1f$pp [$%+.1f$, $%+.1f$]", d, lo, hi)
}

tab <- contrast_df |>
  mutate(rq_short = recode(rq, wording = "Sub-RQ1", split = "Sub-RQ2",
                           interaction = "Sub-RQ3")) |>
  mutate(cell = paste0(fmt_estci(log_odds, ci_lo, ci_hi),
                       " \\newline ",
                       fmt_pp(delta_pp, delta_pp_lo, delta_pp_hi))) |>
  select(display, rq_short, cell) |>
  pivot_wider(names_from = rq_short, values_from = cell) |>
  mutate(display = factor(display, levels = DISPLAY_ORDER)) |>
  arrange(display)

tex_lines <- c(
  "% Auto-generated by analysis/results_pipeline.R. Do not hand-edit.",
  "\\begin{tabular}{lp{4.0cm}p{4.0cm}p{4.0cm}}",
  "\\toprule",
  "Model & Sub-RQ1: wording & Sub-RQ2: split & Sub-RQ3: interaction \\\\",
  "\\midrule"
)
for (i in seq_len(nrow(tab))) {
  tex_lines <- c(
    tex_lines,
    sprintf("%s & %s & %s & %s \\\\",
            tab$display[i], tab$`Sub-RQ1`[i], tab$`Sub-RQ2`[i], tab$`Sub-RQ3`[i])
  )
}
tex_lines <- c(tex_lines, "\\bottomrule", "\\end{tabular}")

if (nzchar(OUT_FIG)) {
  APPENDIX_ART <- file.path(REPO, "report", "appendix_artifacts")
  dir.create(APPENDIX_ART, showWarnings = FALSE, recursive = TRUE)
  writeLines(tex_lines, file.path(APPENDIX_ART, "contrast_table.tex"))
}

cat("\nDone. CSVs in ", OUT_CSV,
    if (nzchar(OUT_FIG)) paste0("; figures in ", OUT_FIG) else "; figures skipped (REPO_FIGURES unset)",
    ".\n", sep = "")
