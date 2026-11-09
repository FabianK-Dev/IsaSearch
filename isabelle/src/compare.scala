/*  Title:      IsaSearch/isabelle/src/compare.scala

Comparison of two benchmark results on identical query texts.
*/

package isabelle.isasearch


import isabelle._


object Benchmark_Comparison {
  import Data._


  /** benchmark results **/

  val metrics = List(
    "Hit@10" -> "top_k_accuracy",
    "MRR" -> "reciprocal_rank",
    "NDCG" -> "normalized_discounted_cumulative_gain"
  )

  // A strategy directory of a run, or a flat result file.
  def load(path: Path): Obj = read(if (path.is_dir) path + Path.basic("results.json") else path)

  private type Key = (String, String)

  private def targets(results: Obj): List[(String, Obj)] =
    results.toList.filter(_._1 != "summary").map { case (target, entry) => target -> obj(entry) }

  private def metadata(entry: Obj): Obj = object_at(entry, "metadata")

  private def skipped(entry: Obj): Boolean = bool(metadata(entry), "skipped")

  private def queries(results: Obj): Map[Key, Obj] =
    (for {
      (target, entry) <- targets(results) if !skipped(entry)
      (kind, query) <- object_at(entry, "queries").toList
    } yield (target, kind) -> obj(query)).toMap

  private def metric(query: Obj, name: String): Double = num(object_at(query, "metrics"), name, 0)

  private def label(results: Obj, target: String): Option[List[String]] =
    metadata(obj(results(target))).get("target_identifier").filter(_ != null)
      .map(l => list(l).map(canonical).sorted)

  private def ordering: Ordering[Key] = Ordering.Tuple2(Ordering.String, Ordering.String)


  /** comparison report **/

  def report(previous: Obj, current: Obj): String = {
    val before = queries(previous)
    val after = queries(current)
    val common = before.keySet.intersect(after.keySet)
    val changed_queries =
      common.filter(key => str(before(key), "query") != str(after(key), "query")).toList
        .sorted(ordering)
    val changed_labels = common.filter { case (target, _) =>
      (label(previous, target), label(current, target)) match {
        case (Some(a), Some(b)) => a != b
        case _ => false
      }
    }.toList.sorted(ordering)
    val matched = (common -- changed_queries -- changed_labels).toList.sorted(ordering)

    def mean(keys: List[Key], queries: Map[Key, Obj], name: String): Double =
      keys.map(key => metric(queries(key), name)).sum / keys.size

    val groups = "All queries" :: matched.map(_._2).distinct.sorted
    val rows = for {
      group <- groups
      keys = matched.filter(key => group == "All queries" || key._2 == group) if keys.nonEmpty
      (name, field) <- metrics
    } yield {
      val old_mean = mean(keys, before, field)
      val new_mean = mean(keys, after, field)
      "| " + group + " | " + keys.size + " | " + name + " | " + Library.format("%.4f", old_mean) +
        " | " + Library.format("%.4f", new_mean) + " | " +
        Library.format("%+.4f", new_mean - old_mean) + " |"
    }
    val changes = matched.flatMap { key =>
      val delta =
        metric(after(key), "reciprocal_rank") - metric(before(key), "reciprocal_rank")
      if (delta != 0) Some(key -> delta) else None
    }.sortBy { case (key, delta) => (delta, key) }(
      Ordering.Tuple2(Ordering.Double.TotalOrdering, ordering))

    def keys_section(title: String, keys: List[Key]): List[String] =
      List("", title + ": " + keys.size + ".") ::: keys.map { case (t, k) => "- " + t + " / " + k }

    def skipped_section(title: String, results: Obj): List[String] = {
      val reasons = targets(results).filter(e => skipped(e._2))
        .groupBy(e => str(metadata(e._2), "skipped_reason", "unspecified"))
        .toList.map { case (reason, entries) => reason -> entries.size }.sorted
      val queries = (for {
        (target, entry) <- targets(results)
        (kind, reason) <- object_at(metadata(entry), "skipped_queries").toList
      } yield (target, kind, reason.toString)).sorted
      List("", title + " skipped targets:") :::
        reasons.map { case (reason, count) => "- " + reason + ": " + count } :::
        (if (queries.isEmpty) Nil
         else
           List("", title + " skipped individual queries:") :::
             queries.map { case (t, k, r) => "- " + t + " / " + k + ": " + r })
    }

    def changes_section(title: String, items: List[(Key, Double)]): List[String] =
      List("", title + ":") ::: items.map { case ((t, k), delta) =>
        "- " + t + " / " + k + ": " + Library.format("%+.4f", delta)
      }

    val lines =
      List(
        "# Benchmark comparison",
        "",
        "Evaluated queries: previous **" + before.size + "**, current **" + after.size +
          "**; matched by target, query type and exact input text, excluding known label " +
          "changes: **" + matched.size + "**.",
        "",
        "The table recomputes both means on those matched queries. Deltas are current minus " +
          "previous; positive is better.",
        "",
        "| Query type | N | Metric | Previous | Current | Delta |",
        "| --- | ---: | --- | ---: | ---: | ---: |"
      ) ::: rows :::
      keys_section("Only in previous", (before.keySet -- after.keySet).toList.sorted(ordering)) :::
      keys_section("Only in current", (after.keySet -- before.keySet).toList.sorted(ordering)) :::
      keys_section("Changed input text (excluded)", changed_queries) :::
      keys_section("Changed relevance labels (excluded)", changed_labels) :::
      skipped_section("Previous", previous) :::
      skipped_section("Current", current) :::
      changes_section("Largest RR regressions", changes.filter(_._2 < 0).take(10)) :::
      changes_section("Largest RR improvements", changes.filter(_._2 > 0).reverse.take(10)) :::
      List(
        "",
        "Legacy results do not record relevance labels, so label equality cannot be verified " +
          "for those runs. Matching queries does not control for corpus contents, models or " +
          "prompts. Check the run manifests. Timing is omitted because cached durations and " +
          "different hardware are not directly comparable."
      )
    lines.mkString("\n") + "\n"
  }

  def run(previous: String, current: String, progress: Progress): Unit = {
    val text = report(load(Path.explode(previous)), load(Path.explode(current)))
    progress.echo("Previous: `" + previous + "`\n\nCurrent: `" + current + "`\n\n" +
      text.stripSuffix("\n"))
  }
}
