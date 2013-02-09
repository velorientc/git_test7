TortoiseHg Documentation

Pro vytvoření dokumentace ve formátu HTML je potřebná instalace sphinx. V Ubuntu je sphinx balíčkem Pythonu. Ve Windows je zřejmě nejlepší easy_install. Sphinx musí být novější než 0.6.

Pro vytvoření souborů PDF jsou potřebné balíčky LaTeX. V Ubuntu to jsou 'texlive-latex-extra' a všechny jeho dependence. Ve Windows je nejlepší MikTeX. 

Jsou-li všechny potřebné rekvizity k disposici, lze použít makefile pro vytvoření cílů: 'make html htmlhelp latex'.

Máme-li 'latex' vybudován, nacédujeme se do jeho výstupního adresáře a spuštěním 'make all-pdf' vytvoříme vlastní soubor PDF.

Máme-li vybudován 'htmlhelp', musíme ve Windows použít jejich  vlastní HTML Help Compiler. 

Pokud ve Window nemáme žádný nástroj 'make', můžeme použít build.bat. Je-li nainstalován HTML Help Compiler a MikTeX, můžeme formáty chm a pdf generovat přímo ('build chm' či 'build pdf').


Formování zdrojového textu
==========================

Následujte prosím tato pravidla při úpravě textů ve zdrojových souborech dokumentace.

- Jak navrženo ve Sphinxu (see http://sphinx.pocoo.org/rest.html#sections),
  použijte:
  
  *************
  Chapter title
  *************

  Section title
  =============

  Subsection title
  ----------------

  Subsubsection title
  ^^^^^^^^^^^^^^^^^^^

- K uvedení klávesy nebo kombinace kláves použijte :kbd:, například:

  :kbd:`Ctrl-A`
  
- K uvedení štítku, tlačítka nebo čehokoli, co se objeví v uživatelském rozhraní, použijte :guilabel:, například:

  :guilabel:`Commit`

- K uvedení nabídky použijte :menuselection: a -->, například:

  :menuselection:`TortoiseHg... --> About`
  
- K uvedení souboru použijte :file:, například:

  :file:`.hg/hgrc`
 
- K uvedení příkazu, zadávaného na příkazovém řádku, použijte :command:, například:

  :command:`hgtk log`

- K uvedení textu, vkládaného do vstupního pole GUI použijte ``, například:

  ``myproxy:8000``

