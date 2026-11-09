/*  Title:      IsaSearch/isabelle/src/release.scala

Released indexes: exported generations, published as GitHub releases by admin/update, and their
download and installation.
*/

package isabelle.isasearch


import isabelle._

import com.github.luben.zstd
import java.io.{BufferedInputStream, DataInputStream, EOFException, FileInputStream, InputStream,
  OutputStream, SequenceInputStream}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, StandardCopyOption}
import scala.jdk.CollectionConverters._


object Release {
  import Data._


  /** releases **/

  // A release is tagged index-NAME-DATE-afp-REVISION, with the AFP revision of its index
  // (hg id -i), and holds a tar archive of the exported generation, compressed by zstd and split
  // into parts NAME.tar.zst.000, ..., with their checksums in SHA256SUMS.
  private val Tag = """index-[A-Za-z0-9_.-]+-(\d{8})-afp-([0-9a-f]+)""".r
  private val Pax_Path = """\d+ path=(.*)""".r
  private val Part = """[A-Za-z0-9_.-]+\.tar\.zst\.\d+""".r
  val checksums = "SHA256SUMS"

  sealed case class Asset(name: String, size: Long, url: String)

  sealed case class Info(tag: String, published: String, assets: List[Asset]) {
    def date: String = tag match { case Tag(date, _) => date case _ => "" }
    def afp: String = tag match { case Tag(_, afp) => afp case _ => "" }
    def parts: List[Asset] = assets.filter(a => Part.matches(a.name)).sortBy(_.name)
    def size: Space = Space.bytes(parts.map(_.size).sum)

    def print: String =
      tag + "  (AFP revision " + afp + ", " + published.take(10) + ", " + size.print + ")"
  }

  private def get(url: String): HTTP.Content =
    try { HTTP.Client.get(Url(url), user_agent = "IsaSearch") }
    catch { case ERROR(msg) => cat_error("Failed to read " + quote(url), msg) }

  // The published releases of an index, newest first, from the GitHub API URL of their
  // repository (option isasearch_releases).
  def releases(url: String): List[Info] = {
    def page(n: Int): List[JSON.T] = list(get(url + "?per_page=100&page=" + n).json)
    val items = Iterator.from(1).map(page).takeWhile(_.nonEmpty).flatten.toList
    val result =
      for {
        item <- items.map(obj)
        if !bool(item, "draft") && !bool(item, "prerelease")
        tag = str(item, "tag_name")
        if Tag.matches(tag)
        assets = list(item.getOrElse("assets", Nil)).map(obj).map(a =>
          Asset(str(a, "name"), JSON.long(a, "size").getOrElse(0L),
            str(a, "browser_download_url")))
        release = Info(tag, str(item, "published_at"), assets)
        if release.parts.nonEmpty && assets.exists(_.name == checksums)
      } yield release
    result.sortBy(_.published).reverse
  }


  /* choice */

  // The revision of the registered AFP, if there is one and it is known.
  def local_afp(): Either[String, String] =
    if (Isabelle_System.getenv("AFP_BASE").isEmpty) Left("No registered AFP")
    else {
      val root = AFP.BASE.expand
      Corpus_Build.revision(root) match {
        case Some(id) => Right(id)
        case None => Left("Unknown revision of the registered AFP " + root.implode)
      }
    }

  // The newest release of an AFP revision; short and full identifiers match by prefix.
  def matching(releases: List[Info], afp_id: String): Option[Info] = {
    val id = afp_id.stripSuffix("+")
    releases.find(r => id.nonEmpty && (id.startsWith(r.afp) || r.afp.startsWith(id)))
  }

  private def interactive: Boolean = {
    val console = System.console()
    console != null && console.isTerminal
  }

  // The release of option -R, else the one of the registered AFP, else the user's choice.
  def choose(releases: List[Info], requested: String, progress: Progress): Info = {
    if (requested.nonEmpty) {
      releases.find(_.tag == requested).getOrElse(
        error("No release " + quote(requested) + "; newest: " + releases.head.tag))
    }
    else {
      val afp = local_afp()
      afp.toOption.flatMap(matching(releases, _)) match {
        case Some(release) =>
          progress.echo("Release for the registered AFP: " + release.print)
          release
        case None =>
          val reason = afp.fold(identity, id => "No release for AFP revision " + id)
          val shown = releases.take(10)
          val listing = shown.zipWithIndex.map { case (r, i) => "  " + (i + 1) + ". " + r.print }
          if (!interactive) {
            error(cat_lines(
              (reason + ". Choose a release with -R TAG, e.g. the newest:") :: listing))
          }
          progress.echo(cat_lines((reason + ". Releases, newest first:") :: listing))
          ask(releases, shown.size)
      }
    }
  }

  @scala.annotation.tailrec
  private def ask(releases: List[Info], shown: Int): Info = {
    print("Release (number or tag, default 1): ")
    System.out.nn.flush()
    val answer = (scala.io.StdIn.readLine(): String | Null) match {
      case line: String => Library.trim_string(line)
      case null => error("No release chosen")
    }
    val chosen =
      if (answer.isEmpty) releases.headOption
      else answer.toIntOption match {
        case Some(n) if 1 <= n && n <= shown => Some(releases(n - 1))
        case _ => releases.find(_.tag == answer)
      }
    chosen match {
      case Some(release) => release
      case None =>
        println("No such release: " + answer)
        ask(releases, shown)
    }
  }


  /** download **/

  // The parts of a release in a directory, each checked against SHA256SUMS. Parts that are
  // there already, from an interrupted download, are kept if they are complete.
  def download(release: Info, dir: Path, progress: Progress): List[Path] = {
    val sums = release.assets.find(_.name == checksums).get
    val expected =
      (for {
        line <- split_lines(get(sums.url).text)
        case List(hash, name) <- Some(space_explode(' ', line).filter(_.nonEmpty))
      } yield name.stripPrefix("*") -> hash).toMap
    Isabelle_System.make_directory(dir)
    for ((part, i) <- release.parts.zipWithIndex) yield {
      val file = dir + Path.basic(part.name)
      val hash = expected.getOrElse(part.name, error("No checksum of " + part.name))
      val label = "part " + (i + 1) + " of " + release.parts.size + " (" +
        Space.bytes(part.size).print + ")"
      if (file.is_file && file_hash(file) == hash) progress.echo("Downloaded " + label)
      else {
        progress.echo("Downloading " + label + " ...")
        val tmp = dir + Path.basic(part.name + ".download")
        val connection = HTTP.Client.open_connection(Url(part.url), user_agent = "IsaSearch")
        try {
          using(connection.getInputStream)(Files.copy(_, tmp.java_path,
            StandardCopyOption.REPLACE_EXISTING))
        }
        catch {
          case exn: java.io.IOException =>
            error("Failed to download " + part.name + ": " + exn.getMessage)
        }
        if (file_hash(tmp) != hash) {
          tmp.file.delete()
          error("Checksum mismatch: " + part.name)
        }
        Files.move(tmp.java_path, file.java_path, StandardCopyOption.REPLACE_EXISTING)
      }
      file
    }
  }


  /* unpack */

  // The tar archive that GNU tar writes for an export: directories and regular files. Names
  // are relative (Data.relative_path), so nothing is written outside the target directory.
  def unpack(parts: List[Path], target: Path): Unit = {
    Zstd.init()
    Isabelle_System.make_directory(target)
    val streams = parts.iterator.map(p => new FileInputStream(p.file): InputStream)
    val input = new SequenceInputStream(streams.asJavaEnumeration)
    using(new DataInputStream(new BufferedInputStream(new zstd.ZstdInputStream(input), 1 << 20))) {
      tar =>
        val header = new Array[Byte](512)
        val buffer = new Array[Byte](1 << 20)

        def field(offset: Int, length: Int): String =
          new String(header, offset, length, StandardCharsets.UTF_8).takeWhile(_ != '\u0000')

        def size: Long =
          if ((header(124) & 0x80) != 0) // GNU base-256
            (125 until 136).foldLeft(0L)((n, i) => (n << 8) | (header(i) & 0xff))
          else java.lang.Long.parseLong(Library.trim_string(field(124, 12)) match {
            case "" => "0" case s => s }, 8)

        def copy(n: Long, out: Option[OutputStream]): Unit = {
          var rest = n
          while (rest > 0) {
            val m = tar.read(buffer, 0, math.min(rest, buffer.length.toLong).toInt)
            if (m < 0) throw new EOFException
            out.foreach(_.write(buffer, 0, m))
            rest -= m
          }
          val padding = (512 - n % 512) % 512
          tar.skipNBytes(padding)
        }

        def text(n: Long): String = {
          val out = new java.io.ByteArrayOutputStream
          copy(n, Some(out))
          out.toString(StandardCharsets.UTF_8)
        }

        var long_name: Option[String] = None
        var finished = false
        while (!finished) {
          tar.readFully(header)
          if (header.forall(_ == 0)) finished = true
          else {
            val name =
              long_name.getOrElse {
                val prefix = if (field(257, 6) == "ustar") field(345, 155) else ""
                if (prefix.isEmpty) field(0, 100) else prefix + "/" + field(0, 100)
              }
            long_name = None
            def path: Path = target + relative_path(name.stripSuffix("/"))
            header(156).toChar match {
              case 'L' => long_name = Some(text(size).takeWhile(_ != '\u0000'))
              case 'x' =>
                long_name = split_lines(text(size)).collectFirst { case Pax_Path(p) => p }
              case 'g' => copy(size, None)
              case '5' => Isabelle_System.make_directory(path)
              case '0' | '\u0000' =>
                val file = path
                Isabelle_System.make_directory(file.dir)
                using(Files.newOutputStream(file.java_path))(out => copy(size, Some(out)))
              case c =>
                error("Unexpected entry in release archive: " + quote(name) + " (" + c + ")")
            }
          }
        }
    }
  }


  /** installation **/

  // Downloads, unpacks and imports a release in a directory of the user's IsaSearch home, on
  // the file system of the indexes, so that the import moves the generation into place. The
  // parts are kept until the import succeeds, so that a new attempt does not download them
  // again.
  def install(url: String, requested: String, name: String, progress: Progress): Path = {
    val published = releases(url)
    if (published.isEmpty) error("No released index at " + url)
    val release = choose(published, requested, progress)
    val dir = home + Path.explode("downloads") + Path.basic(release.tag)
    val parts = download(release, dir, progress)
    val unpacked = dir + Path.basic("unpacked")
    try {
      Isabelle_System.rm_tree(unpacked)
      progress.echo("Unpacking ...")
      unpack(parts, unpacked)
      val source = File.read_dir(unpacked) match {
        case List(single) if (unpacked + Path.basic(single)).is_dir => unpacked + Path.basic(single)
        case _ => error("Expected one exported index in the release archive")
      }
      val result = Index.import_index(source, name, progress)
      Isabelle_System.rm_tree(dir)
      result
    }
    finally { Isabelle_System.rm_tree(unpacked) }
  }
}
