%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Updated 2013-09-13: see notes below.
%
% The file now has some non-standard usage which is worth explaining.
% The Language style sheet makes a distinction between two kinds of
% in-text citations: citing a work and citing an author.
%
% Citing a work:
% - Two authors are joined by an ampersand (&).
% - More than two authors are abbreviated with "et al."
% - No parentheses are placed around the year (though parentheses may
%   contain the whole citation).
%
% Citing an author:
% - Two authors are joined by "and".
% - More than two authors are abbreviated with "and colleagues".
% - The year is surrounded by parentheses (with page numbers, if
%   present).
%
% To provide for both kinds of citations, this style capitalizes on
% the fact that natbib citation commands come in two flavors. In a
% typical style compatible with natbib, ordinary commands such as
% \citet and \citep produce short citations abbreviated with et al.,
% whereas starred commands such as \citet* and \citep* produce a
% citation with a full author list. Since Language does not require
% citations with full authors, this style repurposes the starred
% commands to be used for "citing the author". The following table
% shows how the natbib citation commands work with the current style.
% 
% \citet:    Hale & White Eagle (1980)    Sprouse et al. (2011)
% \citet*:   Hale and White Eagle (1980)  Sprouse and colleagues (2011)
% \citep:    (Hale & White Eagle 1980)    (Sprouse et al. 2011)
% \citep*:   (Hale and White Eagle 1980)  (Sprouse and colleagues 2011)
% \citealt:  Hale & White Eagle 1980      Sprouse et al. 2011
% \citealt*: Hale and White Eagle 1980    Sprouse and colleagues 2011
% \citealp:  Hale & White Eagle 1980      Sprouse et al. 2011
% \citealp*: Hale and White Eagle 1980    Sprouse and colleagues 2011
% \citeauthor:  Hale & White Eagle        Sprouse et al.
% \citeauthor*: Hale and White Eagle      Sprouse and colleagues
%
% Authors of Language articles would typically use \citet*, \citep,
% \citealt and \citeauthor*, though they could use any of the above
% commands. There is no command for giving a full list of authors --
% even the command \citefullauthor will give just "Sprouse and
% colleagues", since it is a synonym of \citeauthor*.
% 
% For the technically inclined, what is happening under the hood is a
% change to the the optional argument of the \bibitem commands that
% are written to the .bbl file. A standard natbib style would write a
% short form to the left of the year in parentheses, and if there are
% more than two authors it would add a full list of authors to the
% right of the parentheses.
%
% \bibitem[{Hale and {White Eagle}(1980)}]{hale}
% \bibitem[{Sprouse et~al.(2011)Sprouse, Wagers, and Phillips}]{sprouse}
%
% The current style writes the "citing the work" form to the left of
% the parentheses and the "citing the author" form to the right of the
% parentheses.
%
% \bibitem[{Hale \& {White Eagle}(1980)Hale and {White Eagle}}]{hale}
% \bibitem[{Sprouse et~al.(2011)Sprouse and colleagues}]{sprouse}
%
% Natbib commands work just as they normally do -- the unstarred
% flavor uses the form to the left of the parentheses, whereas the
% starred flavor uses the form to the right.
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
% BibTeX style file language.bst
%
% Intended for the journal Language (Linguistic Society of America)
% Created by Ron Artstein on 2010/02/26
% For use with <natbib.sty> for author-year citations.
%
% This file produces bibliographies that comply with the Language
% Style Sheet, section 12 (References):
%
% http://www.lsadc.org/info/pubs-lang-style.cfm
%
% The Language style sheet is grossly underspecified: for example, it
% does not say where to place edition numbers, whether and how to
% include chapter numbers, or how to put down the series and volume of
% a monograph. This file was created in a bit of a haste, and I didn't
% check with published articles for all of the details, but rather
% made choices based on my own aesthetic judgement. So it may well be
% that this file does not fully conform with the practice of the
% journal. If there are errors, please let me know and I'll fix them.
% 
% I hope people find this file useful. Please email me with comments 
% and suggestions.
% 
% Ron Artstein
% last name [at] ict.usc.edu
% http://ron.artstein.org/
% February 26, 2010.
%
% Some technical notes.
%
% This file is based on a file generated with the package <custom-bib>
% by Patrick W. Daly (see selected options below), which was then
% manually customized to conform with requirements which cannot be met
% by <custom-bib>. Departures from the generated file include:
%
% Function format.journal.pages: replaced colon ":" with period "." as
% the separator between volume and pages.
%
% Function reverse.pass: changed so that the extra label is enclosed
% in parentheses when the year field ends in an uppercase or lowercase
% letter (change modeled after Uli Sauerland's modification of
% nals.bst).
%
% Changes:
%
% 2010-03-02: I checked this style file by trying to reproduce the
% references in the Language style sheet, and modified this file
% accordingly. It now produces the references perfectly, except that
% it does not lowercase words that follow a colon in the title. This
% is due to the built-in BibTeX function change.case$, and cannot be
% changed through a style file. [Update 2012-06-09: this is no longer
% an issue, since the Language style sheet now uses uppercase for
% words that follow a colon in the title.]
%
% 2010-03-02: Added <custom-bib> option edparxc to put parentheses
% around editor "(ed.)" for edited works without an author, and
% removed option and-com-ed to get rid of a comma between two editors.
%
% 2010-03-02: Functions book, inbook, manual, proceedings: changed
% format.btitle to format.title in order to give sentence-style
% capitalization to the title. [Reversed 2012-06-09]
%
% 2010-03-02: Function format.booktitle: copied code from format.title
% in order to give sentence-style capitalization to the volume title
% of articles in collections and proceedings.
%
% 2010-03-02: Function bbl.edby: changed the text from "edited by" to
% "ed.~by".
%
% 2010-03-02: Functions book, inbook, proceedings: replaced
% format.date with new function format.date.same.block when the date
% comes after an editor, in order to have no period between (ed.) and
% the date.
%
% 2010-03-02: Function bbl.phdthesis: changed the text from
% "Ph.D. thesis" to "dissertation".
%
% 2010-03-02: Function phdthesis: replaced school and address
% statements with new function format.school.address to get "school:
% address" format; moved bbl.phdthesis after format.school.address,
% and changed 'output.state to before.all in order to get rid of the
% comma.
%
% 2010-03-02: Function unpublished: added format.organization.address
% in order to allow an organization and address as in the Miner
% example from the Language style sheet, and removed new.block
% statements between organization/address, url and note in order to
% have them separated by commas rather than periods.
%
% 2010-03-02: There is one quirk of the Language style sheet which I
% will not attempt to reproduce: when specifying a range of page
% numbers, the style sheet omits common large digits, so for example
% an article from pages 117 to 132 will be printed as "117--32". If a
% .bib database is used only for a Language article then this poses no
% problem -- just input the page numbers the way they should be
% printed. If however the same database is used for multiple articles
% then there is a problem, because in a different journal, the same
% page range needs to be printed as "117--132". The proper way to
% handle this would be to always put the full start and stop pages in
% the database, and have the Language bibliography style (this file)
% eliminate the common digits. However, this requires substantial
% BibTeX hacking which I am not prepared to do at the moment.
%
% %%%%%%%%%%%%%%%%%
% Update 2012-06-09
% %%%%%%%%%%%%%%%%%
%
% It was recently brought to my attention that the Language style
% sheet has changed, so I updated the file accordingly (thanks to
% Chris Pinon for alerting me). The main changes are that now author
% names are typeset in small caps and book and journal titles are
% typeset in italics, as in the published journal (the previous
% version required the use of roman type everywhere for
% submissions). There are other changes as well, and altogether this
% affects several <custom-bib> options; the current options can be
% seen in the beginning of the genreated file below. Manual changes
% from the previous version were carried over, except as noted; these
% are described above. Additional manual updates are listed below.
%
% 2012-06-09: Functions book, inbook, manual, proceedings: restored
% format.title to format.btitle as in generated file, because italics
% are now required for books and collection volumes.
%
% 2012-06-09: Function format.btitle: copied code from format.title in
% order to give sentence-style capitalization to the titles of books
% and collection volumes, as done previously for function.booktitle
% (arguably, this would have been the correct way to do it in the
% first place).
%
% 2012-06-09: Function format.names: two lines below the conditional
% "numnames #2 >", replaced 'skip$ with { "," * } in order to have a
% comma before "and" when only two authors are present, as opposed to
% a semicolon before "and" with three or more authors (and no
% punctuation before "and" in the generated file, or in a list of
% editors).
%
% 2012-06-09: Function format.names.ed: replaced semicolon with comma
% (twice) so that editor names are separated by commas rather than
% semicolons (this is not documented in the Language style sheet but
% is consistent with it, and appears to be the case in a recent
% published article: Boye and Harder, Language 88(1):1-44, 2012).
%
% 2012-06-10: Function write.url: removed \newline before URL
%
% 2012-06-10: Function inproceedings: moved stuff around to get the
% correct placement of page numbers. This is mildly interesting so I
% will elaborate on the reasoning (also so that I don't forget it next
% time I'm asked to tweak the style). In conference proceedings, the
% address field in BibTeX can be used for two separate meanings --
% either the location of the conference, or the place of
% publication. According to the Language style sheet, a conference
% location comes right after the title and before the page numbers,
% while the place of publication comes after the page numbers,
% separated by a period. We therefore need to figure out what the
% address field stands for in each particular entry. For this style
% file I adopted a heuristic approach (which only applies for the type
% @inproceedings): if the "publisher" field is present, assume that
% "address" denotes the place of publication, otherwise assume it
% denotes the conference location. This heuristic is rather
% convenient, and not very limiting.
%
% A separate issue with proceedings concerns capitalization. In the
% one example in the Language style sheet, the proceedings title is
% capitalized (title style): "Proceedings of the 4th International
% Conference on Speech Prosody (Speech Prosody 2008)". This stands in
% contrast to all other volume and book titles in the style sheet. So
% the question arises: Are the titles of proceedings volumes to be
% treated differently than all other volume titles, or is this just a
% coincidence because all the content words happen to be proper names
% (in this case, the name of the conference)? A recent published
% article sheds some light but also confusion: Nishiyama and Koenig,
% Lanuage 86(3):611-646, 2012, has both "Proceedings of the 29th
% annual Penn Linguistics Colloquium" as well as "Proceedings of the
% fourth Amsterdam colloquium". This supports the proper name
% hypothesis, since "annual" and "fourth" are in lower case, and
% "Penn" and "Amsterdam" are obviously proper names, though I fail to
% see the difference in proper-name status granted to the two
% colloquia. At any rate, I take it that proceedings titles are to be
% lowercased like any other title, and proper names should be
% individually excluded from lowercasing through the use of braces in
% the BibTeX database. The question of what exactly is a proper name
% in a conference title remains somewhat vague (going back to the
% example from the style sheet, the conference is commonly known as
% "Speech Prosody" so my personal inclination is to consider the
% "international conference" part as not part of the proper name).
%
% 2012-06-10: Function format.note: removed case-changing commands
% since these result in lowercasing of the abbreviation MS following a
% comma. Notes will now appear in uppercase or lowercase exactly as
% entered in the bib database.
%
% 2012-06-10: Function format.lab.names: replaced bbl.and with literal
% ampersand "\&" so that labels used for in-text citations have
% ampersands, as opposed to the word "and" used in the reference
% list. [Additional comment text removed in light of change made on
% 2012-06-12 to format.full.names, see note below].
%
% 2012-06-10: Function format.incoll.inproc.crossref: replaced word.in
% with new function word.crossref.in because unlike in standalone
% collections, cross-referenced collections do require use of the word
% "in".
%
% 2012-06-10: Function format.incoll.inproc.crossref: replaced \cite
% with \citeauthor to avoid citing the year in the cross-reference.
%
% 2012-06-10: Function article: add a space after the journal name
% only if a volume is present, so the journal name will be followed by
% punctuation if there is no volume (useful for a note, but might
% cause problems if there are pages but no volume).
%
% 2012-06-10: Function article: removed new.block before format.note
% so that notes get separated from preceding material by a comma
% rather than a period.
%
% 2012-06-10: Function begin.bib: redefined \url and \urlprefix to do
% nothing and write "Online: " as required, though this is not as
% useful as it could be since these only take effect if corresponding
% commands are not already defined in a LaTeX style file.
%
% 2012-06-12: Function format.full.names: copied and modified code
% from format.lab.names, replacing ampersand "\&" and with bbl.and and
% replacing bbl.etal with "and colleagues" (twice). This allows using
% starred citation commands to produce the alternative forms for
% citing an author, as per the Language style sheet. See usage
% explanation at the top of this file.
%
% 2013-09-13: Function write.url: added a period at the end, as
% required by the Language style (thanks to Todd Hughes for bringing
% this to my attention).
%
% The preamble of the generated file begins below:
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%
%% This is file `language.bst',
%% generated with the docstrip utility.
%%
%% The original source files were:
%%
%% merlin.mbs  (with options: `ay,nat,vonx,nm-revv1,jnrlst,aunm-semi,nmft,nmft-sc,nmand-rm,keyxyr,blkyear,dt-beg,yr-per,note-yr,vnum-x,num-xser,ser-vol,jnm-x,bkpg-x,add-pub,pre-edn,edparxc,edby,in-x,ppx,ed,abr,mth-bare,xedn,url,url-nl,nfss,')
%% ----------------------------------------
%% *** For the journal Language ***
%% 
%% Copyright 1994-2007 Patrick W Daly
 % ===============================================================
 % IMPORTANT NOTICE:
 % This bibliographic style (bst) file has been generated from one or
 % more master bibliographic style (mbs) files, listed above.
 %
 % This generated file can be redistributed and/or modified under the terms
 % of the LaTeX Project Public License Distributed from CTAN
 % archives in directory macros/latex/base/lppl.txt; either
 % version 1 of the License, or any later version.
 % ===============================================================
 % Name and version information of the main mbs file:
 % \ProvidesFile{merlin.mbs}[2007/04/24 4.20 (PWD, AO, DPC)]
 %   For use with BibTeX version 0.99a or later
 %-------------------------------------------------------------------
 % This bibliography style file is intended for texts in ENGLISH
 % This is an author-year citation style bibliography. As such, it is
 % non-standard LaTeX, and requires a special package file to function properly.
 % Such a package is    natbib.sty   by Patrick W. Daly
 % The form of the \bibitem entries is
 %   \bibitem[Jones et al.(1990)]{key}...
 %   \bibitem[Jones et al.(1990)Jones, Baker, and Smith]{key}...
 % The essential feature is that the label (the part in brackets) consists
 % of the author names, as they should appear in the citation, with the year
 % in parentheses following. There must be no space before the opening
 % parenthesis!
 % With natbib v5.3, a full list of authors may also follow the year.
 % In natbib.sty, it is possible to define the type of enclosures that is
 % really wanted (brackets or parentheses), but in either case, there must
 % be parentheses in the label.
 % The \cite command functions as follows:
 %   \citet{key} ==>>                Jones et al. (1990)
 %   \citet*{key} ==>>               Jones, Baker, and Smith (1990)
 %   \citep{key} ==>>                (Jones et al., 1990)
 %   \citep*{key} ==>>               (Jones, Baker, and Smith, 1990)
 %   \citep[chap. 2]{key} ==>>       (Jones et al., 1990, chap. 2)
 %   \citep[e.g.][]{key} ==>>        (e.g. Jones et al., 1990)
 %   \citep[e.g.][p. 32]{key} ==>>   (e.g. Jones et al., p. 32)
 %   \citeauthor{key} ==>>           Jones et al.
 %   \citeauthor*{key} ==>>          Jones, Baker, and Smith
 %   \citeyear{key} ==>>             1990
 %---------------------------------------------------------------------

ENTRY
  { address
    author
    booktitle
    chapter
    edition
    editor
    eid
    howpublished
    institution
    journal
    key
    month
    note
    number
    organization
    pages
    publisher
    school
    series
    title
    type
    url
    volume
    year
  }
  {}
  { label extra.label sort.label short.list }
INTEGERS { output.state before.all mid.sentence after.sentence after.block }
FUNCTION {init.state.consts}
{ #0 'before.all :=
  #1 'mid.sentence :=
  #2 'after.sentence :=
  #3 'after.block :=
}
STRINGS { s t}
FUNCTION {output.nonnull}
{ 's :=
  output.state mid.sentence =
    { ", " * write$ }
    { output.state after.block =
        { add.period$ write$
          newline$
          "\newblock " write$
        }
        { output.state before.all =
            'write$
            { add.period$ " " * write$ }
          if$
        }
      if$
      mid.sentence 'output.state :=
    }
  if$
  s
}
FUNCTION {output}
{ duplicate$ empty$
    'pop$
    'output.nonnull
  if$
}
FUNCTION {output.check}
{ 't :=
  duplicate$ empty$
    { pop$ "empty " t * " in " * cite$ * warning$ }
    'output.nonnull
  if$
}
FUNCTION {fin.entry}
{ add.period$
  write$
  newline$
}

FUNCTION {new.block}
{ output.state before.all =
    'skip$
    { after.block 'output.state := }
  if$
}
FUNCTION {new.sentence}
{ output.state after.block =
    'skip$
    { output.state before.all =
        'skip$
        { after.sentence 'output.state := }
      if$
    }
  if$
}
FUNCTION {add.blank}
{  " " * before.all 'output.state :=
}

FUNCTION {date.block}
{
  new.block
}

FUNCTION {not}
{   { #0 }
    { #1 }
  if$
}
FUNCTION {and}
{   'skip$
    { pop$ #0 }
  if$
}
FUNCTION {or}
{   { pop$ #1 }
    'skip$
  if$
}
STRINGS {z}
FUNCTION {remove.dots}
{ 'z :=
  ""
  { z empty$ not }
  { z #1 #1 substring$
    z #2 global.max$ substring$ 'z :=
    duplicate$ "." = 'pop$
      { * }
    if$
  }
  while$
}
FUNCTION {new.block.checkb}
{ empty$
  swap$ empty$
  and
    'skip$
    'new.block
  if$
}
FUNCTION {field.or.null}
{ duplicate$ empty$
    { pop$ "" }
    'skip$
  if$
}
FUNCTION {emphasize}
{ duplicate$ empty$
    { pop$ "" }
    { "\emph{" swap$ * "}" * }
  if$
}
FUNCTION {scaps}
{ duplicate$ empty$
    { pop$ "" }
    { "\textsc{" swap$ * "}" * }
  if$
}
FUNCTION {bib.name.font}
{ scaps }
FUNCTION {bib.fname.font}
{ bib.name.font }
FUNCTION {tie.or.space.prefix}
{ duplicate$ text.length$ #3 <
    { "~" }
    { " " }
  if$
  swap$
}

FUNCTION {capitalize}
{ "u" change.case$ "t" change.case$ }

FUNCTION {space.word}
{ " " swap$ * " " * }
 % Here are the language-specific definitions for explicit words.
 % Each function has a name bbl.xxx where xxx is the English word.
 % The language selected here is ENGLISH
FUNCTION {bbl.and}
{ "und"}

FUNCTION {bbl.etal}
{ "et~al." }

FUNCTION {bbl.editors}
{ "Hg." }

FUNCTION {bbl.editor}
{ "Hg." }

FUNCTION {bbl.edby}
{ "hrsg.~von" }

FUNCTION {bbl.edition}
{ "Ed." }

FUNCTION {bbl.volume}
{ "Ausg." }

FUNCTION {bbl.of}
{ "von" }

FUNCTION {bbl.number}
{ "Nr." }

FUNCTION {bbl.nr}
{ "Nr." }

FUNCTION {bbl.in}
{ "in" }

FUNCTION {bbl.pages}
{ "" }

FUNCTION {bbl.page}
{ "" }

FUNCTION {bbl.chapter}
{ "Kap." }

FUNCTION {bbl.techrep}
{ "Tech. Rep." }

FUNCTION {bbl.mthesis}
{ "Masterarbeit" }

FUNCTION {bbl.phdthesis}
{ "Dissertation" }

MACRO {jan} {"Jan."}

MACRO {feb} {"Feb."}

MACRO {mar} {"März"}

MACRO {apr} {"Apr."}

MACRO {may} {"Mai"}

MACRO {jun} {"Jun."}

MACRO {jul} {"Jul."}

MACRO {aug} {"Aug."}

MACRO {sep} {"Sep."}

MACRO {oct} {"Oct."}

MACRO {nov} {"Nov."}

MACRO {dec} {"Dec."}

MACRO {acmcs} {"ACM Computing Surveys"}

MACRO {acta} {"Acta Informatica"}

MACRO {cacm} {"Communications of the ACM"}

MACRO {ibmjrd} {"IBM Journal of Research and Development"}

MACRO {ibmsj} {"IBM Systems Journal"}

MACRO {ieeese} {"IEEE Transactions on Software Engineering"}

MACRO {ieeetc} {"IEEE Transactions on Computers"}

MACRO {ieeetcad}
 {"IEEE Transactions on Computer-Aided Design of Integrated Circuits"}

MACRO {ipl} {"Information Processing Letters"}

MACRO {jacm} {"Journal of the ACM"}

MACRO {jcss} {"Journal of Computer and System Sciences"}

MACRO {scp} {"Science of Computer Programming"}

MACRO {sicomp} {"SIAM Journal on Computing"}

MACRO {tocs} {"ACM Transactions on Computer Systems"}

MACRO {tods} {"ACM Transactions on Database Systems"}

MACRO {tog} {"ACM Transactions on Graphics"}

MACRO {toms} {"ACM Transactions on Mathematical Software"}

MACRO {toois} {"ACM Transactions on Office Information Systems"}

MACRO {toplas} {"ACM Transactions on Programming Languages and Systems"}

MACRO {tcs} {"Theoretical Computer Science"}
FUNCTION {bibinfo.check}
{ swap$
  duplicate$ missing$
    {
      pop$ pop$
      ""
    }
    { duplicate$ empty$
        {
          swap$ pop$
        }
        { swap$
          pop$
        }
      if$
    }
  if$
}
FUNCTION {bibinfo.warn}
{ swap$
  duplicate$ missing$
    {
      swap$ "missing " swap$ * " in " * cite$ * warning$ pop$
      ""
    }
    { duplicate$ empty$
        {
          swap$ "empty " swap$ * " in " * cite$ * warning$
        }
        { swap$
          pop$
        }
      if$
    }
  if$
}
FUNCTION {write.url}
{ url empty$
    { skip$ }
    { "\urlprefix\url{" url * "}." * write$ newline$ }
  if$
}

INTEGERS { nameptr namesleft numnames }


STRINGS  { bibinfo}

FUNCTION {format.names}
{ 'bibinfo :=
  duplicate$ empty$ 'skip$ {
  's :=
  "" 't :=
  #1 'nameptr :=
  s num.names$ 'numnames :=
  numnames 'namesleft :=
    { namesleft #0 > }
    { s nameptr
      duplicate$ #1 >
        { "{ff~}{vv~}{ll}{, jj}" }
        { "{vv~}{ll}{, ff}{, jj}" }
      if$
      format.name$
      bib.name.font
      bibinfo bibinfo.check
      't :=
      nameptr #1 >
        {
          namesleft #1 >
            { "; " * t * }
            {
              s nameptr "{ll}" format.name$ duplicate$ "others" =
                { 't := }
                { pop$ }
              if$
              numnames #2 >
                { ";" * }
                { "," * }
              if$
              t "others" =
                {
                  " " * bbl.etal bib.name.font *
                }
                {
                  bbl.and
                  space.word * t *
                }
              if$
            }
          if$
        }
        't
      if$
      nameptr #1 + 'nameptr :=
      namesleft #1 - 'namesleft :=
    }
  while$
  } if$
}
FUNCTION {format.names.ed}
{
  'bibinfo :=
  duplicate$ empty$ 'skip$ {
  's :=
  "" 't :=
  #1 'nameptr :=
  s num.names$ 'numnames :=
  numnames 'namesleft :=
    { namesleft #0 > }
    { s nameptr
      "{ff~}{vv~}{ll}{, jj}"
      format.name$
      bibinfo bibinfo.check
      't :=
      nameptr #1 >
        {
          namesleft #1 >
            { ", " * t * }
            {
              s nameptr "{ll}" format.name$ duplicate$ "others" =
                { 't := }
                { pop$ }
              if$
              numnames #2 >
                { "," * }
                'skip$
              if$
              t "others" =
                {

                  " " * bbl.etal *
                }
                {
                  bbl.and
                  space.word * t *
                }
              if$
            }
          if$
        }
        't
      if$
      nameptr #1 + 'nameptr :=
      namesleft #1 - 'namesleft :=
    }
  while$
  } if$
}
FUNCTION {format.key}
{ empty$
    { key field.or.null }
    { "" }
  if$
}

FUNCTION {format.authors}
{ author "author" format.names
}
FUNCTION {get.bbl.editor}
{ editor num.names$ #1 > 'bbl.editors 'bbl.editor if$ }

FUNCTION {format.editors}
{ editor "editor" format.names duplicate$ empty$ 'skip$
    {
      " " *
      get.bbl.editor
   "(" swap$ * ")" *
      *
    }
  if$
}
FUNCTION {format.note}
{
 note empty$
    { "" }
    { note #1 #1 substring$
      note #2 global.max$ substring$ * "note" bibinfo.check
    }
  if$
}

FUNCTION {format.title}
{ title
  duplicate$ empty$ 'skip$
    { "t" change.case$ }
  if$
  "title" bibinfo.check
}
FUNCTION {format.full.names}
{ 's :=
  "" 't :=
  s #1 "{vv~}{ll}" format.name$
  s num.names$ duplicate$
  #2 >
    { pop$
      " " * "and colleagues" *
    }
    { #2 <
        'skip$
        { s #2 "{ff }{vv }{ll}{ jj}" format.name$ "others" =
            {
              " " * "and colleagues" *
            }
            { bbl.and space.word * s #2 "{vv~}{ll}" format.name$
              * }
          if$
        }
      if$
    }
  if$
}

FUNCTION {author.editor.key.full}
{ author empty$
    { editor empty$
        { key empty$
            { cite$ #1 #3 substring$ }
            'key
          if$
        }
        { editor format.full.names }
      if$
    }
    { author format.full.names }
  if$
}

FUNCTION {author.key.full}
{ author empty$
    { key empty$
         { cite$ #1 #3 substring$ }
          'key
      if$
    }
    { author format.full.names }
  if$
}

FUNCTION {editor.key.full}
{ editor empty$
    { key empty$
         { cite$ #1 #3 substring$ }
          'key
      if$
    }
    { editor format.full.names }
  if$
}

FUNCTION {make.full.names}
{ type$ "book" =
  type$ "inbook" =
  or
    'author.editor.key.full
    { type$ "proceedings" =
        'editor.key.full
        'author.key.full
      if$
    }
  if$
}

FUNCTION {output.bibitem}
{ newline$
  "\bibitem[{" write$
  label write$
  ")" make.full.names duplicate$ short.list =
     { pop$ }
     { * }
   if$
  "}]{" * write$
  cite$ write$
  "}" write$
  newline$
  ""
  before.all 'output.state :=
}

FUNCTION {n.dashify}
{
  't :=
  ""
    { t empty$ not }
    { t #1 #1 substring$ "-" =
        { t #1 #2 substring$ "--" = not
            { "--" *
              t #2 global.max$ substring$ 't :=
            }
            {   { t #1 #1 substring$ "-" = }
                { "-" *
                  t #2 global.max$ substring$ 't :=
                }
              while$
            }
          if$
        }
        { t #1 #1 substring$ *
          t #2 global.max$ substring$ 't :=
        }
      if$
    }
  while$
}

FUNCTION {word.in}
{ "" }

FUNCTION {word.crossref.in}
{ "In" }

FUNCTION {format.date}
{ year "year" bibinfo.check duplicate$ empty$
    {
    }
    'skip$
  if$
  extra.label *
  before.all 'output.state :=
  after.sentence 'output.state :=
}
FUNCTION {format.date.same.block}
{ year "year" bibinfo.check duplicate$ empty$
    {
    }
    'skip$
  if$
  extra.label *
  before.all 'output.state :=
}
FUNCTION {format.btitle}
{ title "title" bibinfo.check
  duplicate$ empty$ 'skip$
    {
      "t" change.case$
      emphasize
    }
  if$
}
FUNCTION {either.or.check}
{ empty$
    'pop$
    { "can't use both " swap$ * " fields in " * cite$ * warning$ }
  if$
}
FUNCTION {format.bvolume}
{ volume empty$
    { "" }
    { bbl.volume volume tie.or.space.prefix
      "volume" bibinfo.check * *
      series "series" bibinfo.check
      duplicate$ empty$ 'pop$
        { emphasize ", " * swap$ * }
      if$
      "volume and number" number either.or.check
    }
  if$
}
FUNCTION {format.number.series}
{ volume empty$
    { number empty$
        { series field.or.null }
        { series empty$
            { number "number" bibinfo.check }
            { output.state mid.sentence =
                { bbl.number }
                { bbl.number capitalize }
              if$
              number tie.or.space.prefix "number" bibinfo.check * *
              bbl.in space.word *
              series "series" bibinfo.check *
            }
          if$
        }
      if$
    }
    { "" }
  if$
}

FUNCTION {format.edition}
{ edition duplicate$ empty$ 'skip$
    {
      output.state mid.sentence =
        { "l" }
        { "t" }
      if$ change.case$
      "edition" bibinfo.check
      " " * bbl.edition *
    }
  if$
}
INTEGERS { multiresult }
FUNCTION {multi.page.check}
{ 't :=
  #0 'multiresult :=
    { multiresult not
      t empty$ not
      and
    }
    { t #1 #1 substring$
      duplicate$ "-" =
      swap$ duplicate$ "," =
      swap$ "+" =
      or or
        { #1 'multiresult := }
        { t #2 global.max$ substring$ 't := }
      if$
    }
  while$
  multiresult
}
FUNCTION {format.pages}
{ pages duplicate$ empty$ 'skip$
    { duplicate$ multi.page.check
        {
          n.dashify
        }
        {
        }
      if$
      "pages" bibinfo.check
    }
  if$
}
FUNCTION {format.journal.pages}
{ pages duplicate$ empty$ 'pop$
    { swap$ duplicate$ empty$
        { pop$ pop$ format.pages }
        {
          "." *
          swap$
          n.dashify
          "pages" bibinfo.check
          *
        }
      if$
    }
  if$
}
FUNCTION {format.journal.eid}
{ eid "eid" bibinfo.check
  duplicate$ empty$ 'pop$
    { swap$ duplicate$ empty$ 'skip$
      {
          ":" *
      }
      if$
      swap$ *
    }
  if$
}
FUNCTION {format.vol.num.pages}
{ volume field.or.null
  duplicate$ empty$ 'skip$
    {
      "volume" bibinfo.check
    }
  if$
  eid empty$
    { format.journal.pages }
    { format.journal.eid }
  if$
}

FUNCTION {format.chapter.pages}
{ chapter empty$
    'format.pages
    { type empty$
        { bbl.chapter }
        { type "l" change.case$
          "type" bibinfo.check
        }
      if$
      chapter tie.or.space.prefix
      "chapter" bibinfo.check
      * *
      pages empty$
        'skip$
        { ", " * format.pages * }
      if$
    }
  if$
}

FUNCTION {format.booktitle}
{ booktitle
  duplicate$ empty$ 'skip$
    { "t" change.case$ }
  if$
  "booktitle" bibinfo.check
  emphasize
}
FUNCTION {format.in.ed.booktitle}
{ format.booktitle duplicate$ empty$ 'skip$
    {
      editor "editor" format.names.ed duplicate$ empty$ 'pop$
        {
          bbl.edby
          " " * swap$ *
          swap$
          "," *
          " " * swap$
          * }
      if$
      word.in swap$ *
    }
  if$
}
FUNCTION {format.thesis.type}
{ type duplicate$ empty$
    'pop$
    { swap$ pop$
      "t" change.case$ "type" bibinfo.check
    }
  if$
}
FUNCTION {format.tr.number}
{ number "number" bibinfo.check
  type duplicate$ empty$
    { pop$ bbl.techrep }
    'skip$
  if$
  "type" bibinfo.check
  swap$ duplicate$ empty$
    { pop$ "t" change.case$ }
    { tie.or.space.prefix * * }
  if$
}
FUNCTION {format.article.crossref}
{
  word.in
  " \cite{" * crossref * "}" *
}
FUNCTION {format.book.crossref}
{ volume duplicate$ empty$
    { "empty volume in " cite$ * "'s crossref of " * crossref * warning$
      pop$ word.in
    }
    { bbl.volume
      capitalize
      swap$ tie.or.space.prefix "volume" bibinfo.check * * bbl.of space.word *
    }
  if$
  " \cite{" * crossref * "}" *
}
FUNCTION {format.incoll.inproc.crossref}
{
  word.crossref.in
  " \citeauthor{" * crossref * "}" *
}
FUNCTION {format.org.or.pub}
{ 't :=
  ""
  address empty$ t empty$ and
    'skip$
    {
      address "address" bibinfo.check *
      t empty$
        'skip$
        { address empty$
            'skip$
            { ": " * }
          if$
          t *
        }
      if$
    }
  if$
}
FUNCTION {format.publisher.address}
{ publisher "publisher" bibinfo.warn format.org.or.pub
}

FUNCTION {format.organization.address}
{ organization "organization" bibinfo.check format.org.or.pub
}

FUNCTION {format.school.address}
{ school "school" bibinfo.warn format.org.or.pub
}

FUNCTION {article}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.title "title" output.check
  new.block
  crossref missing$
    {
      journal
      "journal" bibinfo.check
      emphasize
      "journal" output.check
      volume field.or.null empty$ 
        'skip$
        { add.blank
        }
      if$
      format.vol.num.pages output
    }
    { format.article.crossref output.nonnull
      format.pages output
    }
  if$
  format.note output
  fin.entry
  write.url
}
FUNCTION {book}
{ output.bibitem
  author empty$
    { format.editors "author and editor" output.check
      editor format.key output
      add.blank
      format.date.same.block "year" output.check
    }
    { format.authors output.nonnull
      crossref missing$
        { "author and editor" editor either.or.check }
        'skip$
      if$
      format.date "year" output.check
    }
  if$
  date.block
  format.btitle "title" output.check
  crossref missing$
    { format.bvolume output
      new.block
      format.number.series output
      format.edition output
      new.sentence
      format.publisher.address output
    }
    {
      new.block
      format.book.crossref output.nonnull
    }
  if$
  new.block
  format.note output
  fin.entry
  write.url
}
FUNCTION {booklet}
{ output.bibitem
  format.authors output
  author format.key output
  format.date "year" output.check
  date.block
  format.title "title" output.check
  new.block
  howpublished "howpublished" bibinfo.check output
  address "address" bibinfo.check output
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {inbook}
{ output.bibitem
  author empty$
    { format.editors "author and editor" output.check
      editor format.key output
      add.blank
      format.date.same.block "year" output.check
    }
    { format.authors output.nonnull
      crossref missing$
        { "author and editor" editor either.or.check }
        'skip$
      if$
      format.date "year" output.check
    }
  if$
  date.block
  format.btitle "title" output.check
  crossref missing$
    {
      format.bvolume output
      format.chapter.pages "chapter and pages" output.check
      new.block
      format.number.series output
      format.edition output
      new.sentence
      format.publisher.address output
    }
    {
      format.chapter.pages "chapter and pages" output.check
      new.block
      format.book.crossref output.nonnull
    }
  if$
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {incollection}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.title "title" output.check
  new.block
  crossref missing$
    { format.in.ed.booktitle "booktitle" output.check
      format.bvolume output
      format.number.series output
      format.edition output
      format.chapter.pages output
      new.sentence
      format.publisher.address output
    }
    { format.incoll.inproc.crossref output.nonnull
      format.chapter.pages output
    }
  if$
  new.block
  format.note output
  fin.entry
  write.url
}
FUNCTION {inproceedings}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.title "title" output.check
  new.block
  crossref missing$
    { format.in.ed.booktitle "booktitle" output.check
      format.bvolume output
      format.number.series output
      publisher empty$
        { format.organization.address output 
          format.pages output
        }
        { format.pages output
          new.sentence
          organization "organization" bibinfo.check output
          format.publisher.address output
        }
      if$
    }
    { format.incoll.inproc.crossref output.nonnull
      format.pages output
    }
  if$
  new.block
  format.note output
  fin.entry
  write.url
}
FUNCTION {conference} { inproceedings }
FUNCTION {manual}
{ output.bibitem
  format.authors output
  author format.key output
  format.date "year" output.check
  date.block
  format.btitle "title" output.check
  organization address new.block.checkb
  organization "organization" bibinfo.check output
  address "address" bibinfo.check output
  format.edition output
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {mastersthesis}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.btitle
  "title" output.check
  new.block
  bbl.mthesis format.thesis.type output.nonnull
  school "school" bibinfo.warn output
  address "address" bibinfo.check output
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {misc}
{ output.bibitem
  format.authors output
  author format.key output
  format.date "year" output.check
  date.block
  format.title output
  new.block
  howpublished "howpublished" bibinfo.check output
  new.block
  format.note output
  fin.entry
  write.url
}
FUNCTION {phdthesis}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.btitle
  "title" output.check
  new.block
  format.school.address output
  add.blank
  before.all 'output.state :=
  bbl.phdthesis format.thesis.type output.nonnull
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {proceedings}
{ output.bibitem
  format.editors output
  editor format.key output
  add.blank
  format.date.same.block "year" output.check
  date.block
  format.btitle "title" output.check
  format.bvolume output
  format.number.series output
  new.sentence
  publisher empty$
    { format.organization.address output }
    { organization "organization" bibinfo.check output
      format.publisher.address output
    }
  if$
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {techreport}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.title
  "title" output.check
  new.block
  format.tr.number output.nonnull
  institution "institution" bibinfo.warn output
  address "address" bibinfo.check output
  new.block
  format.note output
  fin.entry
  write.url
}

FUNCTION {unpublished}
{ output.bibitem
  format.authors "author" output.check
  author format.key output
  format.date "year" output.check
  date.block
  format.title "title" output.check
  new.block
  format.organization.address output
  format.note "note" output.check
  fin.entry
  write.url
}

FUNCTION {default.type} { misc }
READ
FUNCTION {sortify}
{ purify$
  "l" change.case$
}
INTEGERS { len }
FUNCTION {chop.word}
{ 's :=
  'len :=
  s #1 len substring$ =
    { s len #1 + global.max$ substring$ }
    's
  if$
}
FUNCTION {format.lab.names}
{ 's :=
  "" 't :=
  s #1 "{vv~}{ll}" format.name$
  s num.names$ duplicate$
  #2 >
    { pop$
      " " * bbl.etal *
    }
    { #2 <
        'skip$
        { s #2 "{ff }{vv }{ll}{ jj}" format.name$ "others" =
            {
              " " * bbl.etal *
            }
            { "\&" space.word * s #2 "{vv~}{ll}" format.name$
              * }
          if$
        }
      if$
    }
  if$
}

FUNCTION {author.key.label}
{ author empty$
    { key empty$
        { cite$ #1 #3 substring$ }
        'key
      if$
    }
    { author format.lab.names }
  if$
}

FUNCTION {author.editor.key.label}
{ author empty$
    { editor empty$
        { key empty$
            { cite$ #1 #3 substring$ }
            'key
          if$
        }
        { editor format.lab.names }
      if$
    }
    { author format.lab.names }
  if$
}

FUNCTION {editor.key.label}
{ editor empty$
    { key empty$
        { cite$ #1 #3 substring$ }
        'key
      if$
    }
    { editor format.lab.names }
  if$
}

FUNCTION {calc.short.authors}
{ type$ "book" =
  type$ "inbook" =
  or
    'author.editor.key.label
    { type$ "proceedings" =
        'editor.key.label
        'author.key.label
      if$
    }
  if$
  'short.list :=
}

FUNCTION {calc.label}
{ calc.short.authors
  short.list
  "("
  *
  year duplicate$ empty$
  short.list key field.or.null = or
     { pop$ "" }
     'skip$
  if$
  *
  'label :=
}

FUNCTION {sort.format.names}
{ 's :=
  #1 'nameptr :=
  ""
  s num.names$ 'numnames :=
  numnames 'namesleft :=
    { namesleft #0 > }
    { s nameptr
      "{ll{ }}{  ff{ }}{  jj{ }}"
      format.name$ 't :=
      nameptr #1 >
        {
          "   "  *
          namesleft #1 = t "others" = and
            { "zzzzz" * }
            { t sortify * }
          if$
        }
        { t sortify * }
      if$
      nameptr #1 + 'nameptr :=
      namesleft #1 - 'namesleft :=
    }
  while$
}

FUNCTION {sort.format.title}
{ 't :=
  "A " #2
    "An " #3
      "The " #4 t chop.word
    chop.word
  chop.word
  sortify
  #1 global.max$ substring$
}
FUNCTION {author.sort}
{ author empty$
    { key empty$
        { "to sort, need author or key in " cite$ * warning$
          ""
        }
        { key sortify }
      if$
    }
    { author sort.format.names }
  if$
}
FUNCTION {author.editor.sort}
{ author empty$
    { editor empty$
        { key empty$
            { "to sort, need author, editor, or key in " cite$ * warning$
              ""
            }
            { key sortify }
          if$
        }
        { editor sort.format.names }
      if$
    }
    { author sort.format.names }
  if$
}
FUNCTION {editor.sort}
{ editor empty$
    { key empty$
        { "to sort, need editor or key in " cite$ * warning$
          ""
        }
        { key sortify }
      if$
    }
    { editor sort.format.names }
  if$
}
FUNCTION {presort}
{ calc.label
  label sortify
  "    "
  *
  type$ "book" =
  type$ "inbook" =
  or
    'author.editor.sort
    { type$ "proceedings" =
        'editor.sort
        'author.sort
      if$
    }
  if$
  #1 entry.max$ substring$
  'sort.label :=
  sort.label
  *
  "    "
  *
  title field.or.null
  sort.format.title
  *
  #1 entry.max$ substring$
  'sort.key$ :=
}

ITERATE {presort}
SORT
STRINGS { last.label next.extra }
INTEGERS { last.extra.num number.label }
FUNCTION {initialize.extra.label.stuff}
{ #0 int.to.chr$ 'last.label :=
  "" 'next.extra :=
  #0 'last.extra.num :=
  #0 'number.label :=
}
FUNCTION {forward.pass}
{ last.label label =
    { last.extra.num #1 + 'last.extra.num :=
      last.extra.num int.to.chr$ 'extra.label :=
    }
    { "a" chr.to.int$ 'last.extra.num :=
      "" 'extra.label :=
      label 'last.label :=
    }
  if$
  number.label #1 + 'number.label :=
}
FUNCTION {reverse.pass}
{ next.extra "b" =
    { "a" 'extra.label := }
    'skip$
  if$
  extra.label 'next.extra :=
  extra.label
  duplicate$ empty$
    'skip$
    { year field.or.null #-1 #1 substring$ chr.to.int$ #65 < 
      { "{\natexlab{" swap$ * "}}" * }
      { "{(\natexlab{" swap$ * "})}" * }
    if$ }
  if$
  'extra.label :=
  label extra.label * 'label :=
}
EXECUTE {initialize.extra.label.stuff}
ITERATE {forward.pass}
REVERSE {reverse.pass}
FUNCTION {bib.sort.order}
{ sort.label
  "    "
  *
  year field.or.null sortify
  *
  "    "
  *
  title field.or.null
  sort.format.title
  *
  #1 entry.max$ substring$
  'sort.key$ :=
}
ITERATE {bib.sort.order}
SORT
FUNCTION {begin.bib}
{ preamble$ empty$
    'skip$
    { preamble$ write$ newline$ }
  if$
  "\begin{thebibliography}{" number.label int.to.str$ * "}" *
  write$ newline$
  "\providecommand{\natexlab}[1]{#1}"
  write$ newline$
  "\providecommand{\url}{\relax}"
  write$ newline$
  "\providecommand{\urlprefix}{Online: }"
  write$ newline$
}
EXECUTE {begin.bib}
EXECUTE {init.state.consts}
ITERATE {call.type$}
FUNCTION {end.bib}
{ newline$
  "\end{thebibliography}" write$ newline$
}
EXECUTE {end.bib}
%% End of customized bst file
%%
%% End of file `language.bst'.

