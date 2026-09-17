/*  Title:      IsaSearch/isabelle/src/duplicate_report.scala

Duplicate report views derived from saved evidence, matching src/duplicate_report.py.
*/

package isabelle.isasearch


import isabelle._


object Duplicate_Report {
  import Data._


  /** text and source links **/

  def markdown_text(text: String): String = {
    val escaped = text.split("(?U)\\s+").filter(_.nonEmpty).mkString(" ")
      .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped.flatMap(c => if ("\\`*_{}[]()#+.!|~-".contains(c)) "\\" + c else c.toString)
  }

  private def usable(url: String): Boolean = url.nonEmpty && url != "#"

  def markdown_link(text: String, url: String): String = {
    val label = markdown_text(text)
    if (!usable(url)) label
    else {
      val safe = ":/?#[]@!$&*+,;=%_-~."
      val encoded = url.getBytes(java.nio.charset.StandardCharsets.UTF_8).map { byte =>
        val n = byte & 255
        val c = n.toChar
        if (n < 128 && (c.isLetterOrDigit || safe.contains(c))) c.toString
        else "%%%02X".format(n)
      }.mkString
      "[" + label + "](<" + encoded + ">)"
    }
  }

  private def document_url(doc: Obj): String =
    List("remote_url", "theory_url").map(str(doc, _)).find(usable).getOrElse("")

  private def location(doc: Obj): (String, String) = {
    val saved = str(doc, "entry")
    val e = if (saved.nonEmpty) saved else entry(str(doc, "id"))
    if (e.nonEmpty) (e, str(doc, "entry_url"))
    else {
      val path = str(doc, "id").split("\\|", 2).head
      (path.replaceFirst("^ISABELLE_HOME/", "Isabelle/"), document_url(doc))
    }
  }

  private def source(text: String, indent: String = ""): List[String] = {
    val fence = "`" * ("`+".r.findAllIn(text).map(_.length + 1).toList :+ 3).max
    List(indent + fence + "isabelle") :::
      text.trim.linesIterator.map(indent + _).toList ::: List(indent + fence)
  }

  private def decimal(value: JSON.T, places: Int): String =
    java.lang.String.format(java.util.Locale.ROOT, "%." + places + "f", Double.box(number(value)))

  private def display(value: JSON.T): String = if (value == null) "None" else JSON.Format(value)


  /** filtered Markdown views **/

  def render(report: Obj, near_exact_only: Boolean = false): String = {
    val tiers = Duplicates.tiers.map(_.name)
      .filter(t => !near_exact_only || t == Duplicate_Tier.Near_Exact.name)
    val thresholds = object_at(report, "thresholds")
    val lines = scala.collection.mutable.ListBuffer[String](
      "# Duplicate analysis: " + (if (near_exact_only) "Near-exact matches" else "Possible duplicates"),
      "",
      "Generated at " + markdown_text(str(report, "generated_at")) + ".",
      "",
      "The selected AFP entries are compared with the indexed AFP and Isabelle library. " +
        "Matches within the source entry are excluded. The tiers guide human review; " +
        "semantic or syntactic similarity does not establish logical duplication.",
      "",
      if (near_exact_only) "This report contains only **near-exact** candidates."
      else "This report includes **possible**, **likely**, and **near-exact** candidates. " +
        "Unclassified neighbours are omitted. Candidate links open the source or library theory; " +
        "the separate near-exact report includes candidate source excerpts for closer inspection.",
      "",
      "Source blocks are excerpts and may end mid-statement; follow the links for complete source.",
      "",
      "Tiers:",
      "",
      "- `near-exact`: distance ≤ " + thresholds("strong_distance") +
        " or syntactic similarity ≥ " + thresholds("syntactic") + "."
    )
    if (!near_exact_only) lines ++= List(
      "- `likely`: the LLM judged the pair to be a duplicate.",
      "- `possible`: distance ≤ " + thresholds("distance") + "."
    )
    lines += ""
    if (!bool(report, "llm_judge")) lines ++= List(
      "LLM judging was disabled. Tiers use only distance and syntactic similarity.", "")
    if (bool(report, "cross")) lines ++= List(
      "Cross-kind matching is enabled: each document was compared with both definitions " +
        "and theorems. Synthetic-control recall is not comparable with a run without cross-kind matching.",
      ""
    )
    object_at(report, "sections").foreach { case (kind, value) =>
      val section = obj(value)
      val entries = list(section("entries")).map(obj).map { e =>
        val items = list(e("items")).map(obj).flatMap { item =>
          val cs = list(item("candidates")).map(obj).filter(c => tiers.contains(str(c, "tier")))
          if (cs.isEmpty) None
          else Some(item ++ Map(
            "candidates" -> cs,
            "best_tier" -> tiers.find(t => cs.exists(c => str(c, "tier") == t)).get
          ))
        }
        e.updated("items", items)
      }
      val items = entries.flatMap(e => list(e("items")).map(obj))
      val candidates = items.flatMap(i => list(i("candidates")).map(obj))
      val summary = object_at(section, "aggregates")
      lines ++= List(
        "## " + markdown_text(kind.capitalize), "",
        items.size + " of " + num(summary, "documents", 0).toInt + " analysed " + markdown_text(kind) +
          " have matches in this report (" + candidates.size + " candidate pairs).", "",
        "Candidate tiers: " + tiers.map(t =>
          candidates.count(c => str(c, "tier") == t) + " " + t).mkString(", ") + ".", ""
      )
      val failures = num(summary, "judge_failures", 0).toInt
      if (failures > 0) lines ++= List(
        "Warning: " + failures + " candidate pairs remain unjudged in the full run " +
          "after LLM request failures. Their tiers use only distance and syntactic similarity. " +
          "Rerunning retries these pairs.", ""
      )
      val control = object_at(section, "self_retrieval")
      lines ++= List(
        "Full-run positive control: " + num(control, "self_retrieved", 0).toInt + " of " + num(control, "documents", 0).toInt +
          " documents retrieved themselves at a distance of about 0 " +
          "(mean self distance " + display(control("mean_self_distance")) + ").", ""
      )
      val truth = object_at(section, "synthetic_ground_truth")
      if (num(truth, "documents_with_known_duplicate", 0) > 0) lines ++= List(
        "Full-run synthetic control: " + num(truth, "documents_recovered", 0).toInt + " of " +
          num(truth, "documents_with_known_duplicate", 0).toInt + " documents with a syntactically " +
          "near-identical counterpart in another entry were recovered within the top " +
          num(thresholds, "top_k", 0).toInt + " (recall " + decimal(truth("recall"), 2) + ").", ""
      )
      val locations = scala.collection.mutable.LinkedHashMap.empty[String, (String, Int)]
      candidates.foreach { c =>
        val (label, url) = location(c)
        locations(label) = (url, locations.get(label).map(_._2).getOrElse(0) + 1)
      }
      if (locations.nonEmpty) {
        lines ++= List("Most frequent match locations in this report:", "")
        locations.toList.sortBy(-_._2._2).take(20).foreach { case (label, (url, count)) =>
          lines += "- " + markdown_link(label, url) + ": " + count + " candidate pairs"
        }
        lines += ""
      }
      entries.foreach { e =>
        val local = list(e("items")).map(obj)
        val date = str(e, "date")
        lines ++= List(
          "### " + markdown_text(str(e, "entry")) + " (" +
            markdown_text(if (date.nonEmpty) date else "unknown date") + ")", "",
          local.size + " of " + num(e, "documents", 0).toInt + " " + markdown_text(kind) +
            " have at least one candidate in this report.", ""
        )
        local.foreach { item =>
          def title(d: Obj): String = {
            val name = str(d, "entity_kname")
            if (name.nonEmpty) name else str(d, "id")
          }
          lines ++= List(
            "#### " + markdown_link(title(item), document_url(item)) + " — " + str(item, "best_tier"),
            ""
          ) ::: source(str(item, "src")) ::: List("")
          list(item("candidates")).map(obj).foreach { c =>
            val (label, url) = location(c)
            val verdict = str(c, "verdict")
            val command = str(c, "command")
            lines += "- **" + str(c, "tier") + "** (" +
              markdown_text(if (command.nonEmpty) command else str(c, "kind")) + ") " +
              markdown_link(title(c), document_url(c)) + " in " + markdown_link(label, url) +
              " (distance " + decimal(c("distance"), 4) +
              ", syntactic " + decimal(c("syntactic_similarity"), 2) +
              (if (verdict.nonEmpty) ", verdict " + markdown_text(verdict) else "") + ")"
            if (str(c, "justification").nonEmpty)
              lines ++= List("", "    " + markdown_text(str(c, "justification")))
            if (str(c, "judge_error").nonEmpty) lines ++= List(
              "", "    **Unjudged: LLM request failed.** " + markdown_text(str(c, "judge_error")))
            if (near_exact_only) lines ++= List("") ::: source(str(c, "src"), "    ")
            lines += ""
          }
        }
      }
    }
    lines.mkString("\n") + "\n"
  }

  def write_views(report: Obj, target: Path): Unit =
    for ((name, exact) <- List(("possible", false), ("near-exact", true))) {
      val path = target.dir + Path.basic(target.base.file_name + "_" + name + ".md")
      File.write(path, render(report, near_exact_only = exact))
    }
}
