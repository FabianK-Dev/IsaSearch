/*  Title:      IsaSearch/isabelle/src/core.scala

Portable data, text preparation, and configuration.
*/

package isabelle.isasearch


import isabelle._

import java.nio.{ByteBuffer, ByteOrder}
import java.nio.file.{Files, StandardCopyOption}
import java.security.MessageDigest


object Data {
  /** JSON values **/

  type Obj = JSON.Object.T

  def obj(x: JSON.T): Obj = JSON.Object.unapply(x).getOrElse(error("Expected JSON object"))

  def list(x: JSON.T): List[JSON.T] = x match {
    case xs: List[_] => xs
    case _ => error("Expected JSON array")
  }

  def str(m: Obj, k: String, default: String = ""): String =
    if (m.get(k).contains(null)) default
    else JSON.string_default(m, k, default).getOrElse(error("Expected string: " + k))

  def bool(m: Obj, k: String, default: Boolean = false): Boolean =
    JSON.bool_default(m, k, default).getOrElse(error("Expected boolean: " + k))

  def number(x: JSON.T): Double = JSON.Value.Double.unapply(x).getOrElse(error("Expected number"))

  def num(m: Obj, k: String, default: Double): Double = m.get(k).map(number).getOrElse(default)

  def strings(m: Obj, k: String): List[String] =
    JSON.strings_default(m, k).getOrElse(error("Expected string array: " + k))

  def object_at(m: Obj, k: String): Obj = m.get(k).map(obj).getOrElse(Map.empty)


  /** JSON files **/

  def read(p: Path): Obj = JSON.Object.parse(File.read(p))

  def write(p: Path, x: JSON.T): Unit = {
    Isabelle_System.make_directory(p.dir)
    val tmp = p.dir + Path.basic(p.file_name + "." + UUID.random_string() + ".tmp")
    File.write(tmp, JSON.Format(x) + "\n")
    Files.move(tmp.java_path, p.java_path,
      StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
  }


  /** checksums **/

  def hash(bytes: Array[Byte]): String =
    MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString

  def hash(s: String): String = hash(s.getBytes(java.nio.charset.StandardCharsets.UTF_8))

  def file_hash(p: Path): String = {
    val md = MessageDigest.getInstance("SHA-256")
    using(Files.newInputStream(p.java_path)) { in =>
      val b = new Array[Byte](65536)
      var n = in.read(b)
      while (n >= 0) {
        if (n > 0) md.update(b, 0, n)
        n = in.read(b)
      }
    }
    md.digest().map(b => f"${b & 255}%02x").mkString
  }

  def canonical(x: JSON.T): String = {
    def ordered(value: JSON.T): JSON.T = value match {
      case JSON.Object(m) =>
        scala.collection.immutable.ListMap.from(m.toList.sortBy(_._1).map { case (k, v) =>
          k -> ordered(v)
        })
      case xs: List[_] => xs.map(ordered)
      case other => other
    }

    JSON.Format(ordered(x))
  }


  /** vectors **/

  def floats(bytes: Array[Byte]): Array[Float] = {
    require(bytes.length % java.lang.Float.BYTES == 0)
    val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    Array.fill(bytes.length / java.lang.Float.BYTES)(b.getFloat())
  }

  def bytes(v: Array[Float]): Array[Byte] = {
    val b = ByteBuffer.allocate(v.length * java.lang.Float.BYTES).order(ByteOrder.LITTLE_ENDIAN)
    v.foreach(b.putFloat)
    b.array()
  }

  def validate(v: Array[Float], dim: Int, metric: Distance_Metric): Unit = {
    if (dim <= 0 || v.length != dim || v.exists(x => !java.lang.Float.isFinite(x)))
      error("Invalid embedding: expected " + dim + " finite float32 values")
    if (metric == Distance_Metric.Cosine && v.forall(_ == 0))
      error("Cosine embedding cannot be zero")
  }

  def distance(a: Array[Float], b: Array[Float], metric: Distance_Metric): Double = {
    require(a.length == b.length)
    var dot = 0.0
    var aa = 0.0
    var bb = 0.0
    var sq = 0.0
    for (i <- a.indices) {
      val x = a(i).toDouble
      val y = b(i).toDouble
      dot += x * y
      aa += x * x
      bb += y * y
      sq += (x - y) * (x - y)
    }
    if (metric == Distance_Metric.Squared_Euclidean) sq
    else math.max(0.0, 1.0 - dot / math.sqrt(aa * bb))
  }


  /** prompt text **/

  def marked(s: String): String = {
    val start = s.indexOf(Prompt.Begin)
    val text = if (start >= 0) s.substring(start + Prompt.Begin.length) else s
    val end = text.indexOf(Prompt.End)
    (if (end >= 0) text.substring(0, end) else text).trim
  }

  def template(s: String, values: Map[String, String]): String = {
    val out = new StringBuilder
    var i = 0
    while (i < s.length) {
      if (s.startsWith("{{", i)) {
        out.append('{')
        i += 2
      }
      else if (s.startsWith("}}", i)) {
        out.append('}')
        i += 2
      }
      else if (s(i) == '{') {
        val end = s.indexOf('}', i)
        if (end < 0) error("Unclosed prompt placeholder")
        val key = s.substring(i + 1, end)
        out.append(values.getOrElse(key, error("Unknown prompt placeholder: " + key)))
        i = end + 1
      }
      else {
        out.append(s(i))
        i += 1
      }
    }
    out.toString
  }

  def truncate(s: String, n: Int): String =
    s.substring(0, s.offsetByCodePoints(0, math.min(n, s.codePointCount(0, s.length))))


  /** paths **/

  def entry(id: String): String =
    id.split("/thys/", 2).lift(1).map(_.takeWhile(_ != '/')).getOrElse("")

  def safe_name(s: String): String = {
    if (!s.matches("[A-Za-z0-9][A-Za-z0-9_.-]*")) error("Invalid index name: " + s)
    s
  }

  def home: Path = Path.explode("$ISASEARCH_HOME_USER")

  def component: Path = Path.explode("$ISASEARCH_HOME")
}


object Text_Preparation {
  private val proof = "(?<![A-Za-z0-9_'])proof(?![A-Za-z0-9_'])".r
  lazy val stopwords: Set[String] =
    File.read(Data.component + Path.explode("benchmark/stopwords_english.txt")).linesIterator.toSet

  def strip_proof(source: String): String =
    proof.findFirstMatchIn(source).map(m => source.substring(0, m.start)).getOrElse(source)

  def metadata(text: String): String = text
    .toLowerCase(java.util.Locale.ROOT)
    .replace('\n', ' ')
    .replaceAll("\\b[a-z]{1,3}\\b|[^a-z ]", " ")
    .split("\\s+")
    .filter(w => w.nonEmpty && !stopwords(w))
    .mkString(" ")
}


case class Config(values: Data.Obj, base: Path = Path.current) {
  import Data._

  def string(k: String, default: String = ""): String = str(values, k, default)

  def boolean(k: String, default: Boolean = false): Boolean = bool(values, k, default)

  def number(k: String, default: Double): Double = num(values, k, default)

  def integer(k: String, default: Int): Int = {
    val n = number(k, default)
    if (!n.isValidInt || n < 0) error("Expected nonnegative integer: " + k)
    n.toInt
  }

  def positive(k: String, default: Int): Int = {
    val n = integer(k, default)
    if (n == 0) error("Expected positive integer: " + k)
    n
  }

  def path(k: String, default: String): Path = {
    val p = Path.explode(string(k, default))
    if (p.is_absolute) p else base + p
  }

  def updated(k: String, v: JSON.T): Config = copy(values = values.updated(k, v))

  def public_values: Data.Obj = {
    def redact(x: JSON.T): JSON.T = x match {
      case JSON.Object(m) =>
        m.filterNot { case (k, _) =>
          val key = k.toLowerCase
          key.contains("api_key") || key.contains("password") ||
          key == "authorization" || key == "token"
        }.view
          .mapValues(redact)
          .toMap
      case xs: List[_] => xs.map(redact)
      case other => other
    }

    obj(redact(values))
  }
}
