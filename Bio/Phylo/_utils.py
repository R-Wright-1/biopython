# Copyright (C) 2009 by Eric Talevich (eric.talevich@gmail.com)
#
# This file is part of the Biopython distribution and governed by your
# choice of the "Biopython License Agreement" or the "BSD 3-Clause License".
# Please see the LICENSE file that should have been included as part of this
# package.

"""Utilities for handling, displaying and exporting Phylo trees.

Third-party libraries are loaded when the corresponding function is called.
"""

import math
import sys

from Bio import MissingPythonDependencyError


def to_networkx(tree):
    """Convert a Tree object to a networkx graph.

    The result is useful for graph-oriented analysis, and also interactive
    plotting with pylab, matplotlib or pygraphviz, though the resulting diagram
    is usually not ideal for displaying a phylogeny.

    Requires NetworkX version 0.99 or later.
    """
    try:
        import networkx
    except ImportError:
        raise MissingPythonDependencyError(
            "Install NetworkX if you want to use to_networkx."
        ) from None

    # NB (1/2010): the networkx API stabilized at v.1.0
    # 1.0+: edges accept arbitrary data as kwargs, weights are floats
    # 0.99: edges accept weight as a string, nothing else
    # pre-0.99: edges accept no additional data
    # Ubuntu Lucid LTS uses v0.99, let's support everything
    if networkx.__version__ >= "1.0":

        def add_edge(graph, n1, n2):
            graph.add_edge(n1, n2, weight=n2.branch_length or 1.0)
            # Copy branch color value as hex, if available
            if hasattr(n2, "color") and n2.color is not None:
                graph[n1][n2]["color"] = n2.color.to_hex()
            elif hasattr(n1, "color") and n1.color is not None:
                # Cascading color attributes
                graph[n1][n2]["color"] = n1.color.to_hex()
                n2.color = n1.color
            # Copy branch weight value (float) if available
            if hasattr(n2, "width") and n2.width is not None:
                graph[n1][n2]["width"] = n2.width
            elif hasattr(n1, "width") and n1.width is not None:
                # Cascading width attributes
                graph[n1][n2]["width"] = n1.width
                n2.width = n1.width

    elif networkx.__version__ >= "0.99":

        def add_edge(graph, n1, n2):
            graph.add_edge(n1, n2, (n2.branch_length or 1.0))

    else:

        def add_edge(graph, n1, n2):
            graph.add_edge(n1, n2)

    def build_subgraph(graph, top):
        """Walk down the Tree, building graphs, edges and nodes."""
        for clade in top:
            graph.add_node(clade.root)
            add_edge(graph, top.root, clade.root)
            build_subgraph(graph, clade)

    if tree.rooted:
        G = networkx.DiGraph()
    else:
        G = networkx.Graph()
    G.add_node(tree.root)
    build_subgraph(G, tree.root)
    return G


def draw_ascii(tree, file=None, column_width=80):
    """Draw an ascii-art phylogram of the given tree.

    The printed result looks like::

                                        _________ Orange
                         ______________|
                        |              |______________ Tangerine
          ______________|
         |              |          _________________________ Grapefruit
        _|              |_________|
         |                        |______________ Pummelo
         |
         |__________________________________ Apple


    :Parameters:
        file : file-like object
            File handle opened for writing the output drawing. (Default:
            standard output)
        column_width : int
            Total number of text columns used by the drawing.

    """
    if file is None:
        file = sys.stdout

    taxa = tree.get_terminals()
    # Some constants for the drawing calculations
    max_label_width = max(len(str(taxon)) for taxon in taxa)
    drawing_width = column_width - max_label_width - 1
    drawing_height = 2 * len(taxa) - 1

    def get_col_positions(tree):
        """Create a mapping of each clade to its column position."""
        depths = tree.depths()
        # If there are no branch lengths, assume unit branch lengths
        if max(depths.values()) == 0:
            depths = tree.depths(unit_branch_lengths=True)
        # Potential drawing overflow due to rounding -- 1 char per tree layer
        fudge_margin = int(math.ceil(math.log(len(taxa), 2)))
        cols_per_branch_unit = (drawing_width - fudge_margin) / float(
            max(depths.values())
        )
        return {
            clade: int(blen * cols_per_branch_unit + 1.0)
            for clade, blen in depths.items()
        }

    def get_row_positions(tree):
        positions = {taxon: 2 * idx for idx, taxon in enumerate(taxa)}

        def calc_row(clade):
            for subclade in clade:
                if subclade not in positions:
                    calc_row(subclade)
            positions[clade] = (
                positions[clade.clades[0]] + positions[clade.clades[-1]]
            ) // 2

        calc_row(tree.root)
        return positions

    col_positions = get_col_positions(tree)
    row_positions = get_row_positions(tree)
    char_matrix = [[" " for x in range(drawing_width)] for y in range(drawing_height)]

    def draw_clade(clade, startcol):
        thiscol = col_positions[clade]
        thisrow = row_positions[clade]
        # Draw a horizontal line
        for col in range(startcol, thiscol):
            char_matrix[thisrow][col] = "_"
        if clade.clades:
            # Draw a vertical line
            toprow = row_positions[clade.clades[0]]
            botrow = row_positions[clade.clades[-1]]
            for row in range(toprow + 1, botrow + 1):
                char_matrix[row][thiscol] = "|"
            # NB: Short terminal branches need something to stop rstrip()
            if (col_positions[clade.clades[0]] - thiscol) < 2:
                char_matrix[toprow][thiscol] = ","
            # Draw descendents
            for child in clade:
                draw_clade(child, thiscol + 1)

    draw_clade(tree.root, 0)
    # Print the complete drawing
    for idx, row in enumerate(char_matrix):
        line = "".join(row).rstrip()
        # Add labels for terminal taxa in the right margin
        if idx % 2 == 0:
            line += " " + str(taxa[idx // 2])
        file.write(line + "\n")
    file.write("\n")


def draw(
    tree,
    label_func=str,
    do_show=True,
    show_confidence=True,
    # For power users
    axes=None,
    branch_labels=None,
    label_colors=None,
    orient_tree='vertical',
    horizontal_direction='down',
    vertical_direction='right',
    circular_span=355,
    draw_labels=True,
    align_labels=False,
    *args,
    **kwargs
):
    """Plot the given tree using matplotlib (or pylab).

    The graphic is a rooted tree, drawn with roughly the same algorithm as
    draw_ascii.

    Additional keyword arguments passed into this function are used as pyplot
    options. The input format should be in the form of:
    pyplot_option_name=(tuple), pyplot_option_name=(tuple, dict), or
    pyplot_option_name=(dict).

    Example using the pyplot options 'axhspan' and 'axvline'::

        from Bio import Phylo, AlignIO
        from Bio.Phylo.TreeConstruction import DistanceCalculator, DistanceTreeConstructor
        constructor = DistanceTreeConstructor()
        aln = AlignIO.read(open('TreeConstruction/msa.phy'), 'phylip')
        calculator = DistanceCalculator('identity')
        dm = calculator.get_distance(aln)
        tree = constructor.upgma(dm)
        Phylo.draw(tree, axhspan=((0.25, 7.75), {'facecolor':'0.5'}),
        ... axvline={'x':0, 'ymin':0, 'ymax':1})

    Visual aspects of the plot can also be modified using pyplot's own functions
    and objects (via pylab or matplotlib). In particular, the pyplot.rcParams
    object can be used to scale the font size (rcParams["font.size"]) and line
    width (rcParams["lines.linewidth"]).

    :Parameters:
        label_func : callable
            A function to extract a label from a node. By default this is str(),
            but you can use a different function to select another string
            associated with each node. If this function returns None for a node,
            no label will be shown for that node.
        do_show : bool
            Whether to show() the plot automatically.
        show_confidence : bool
            Whether to display confidence values, if present on the tree.
        axes : matplotlib/pylab axes
            If a valid matplotlib.axes.Axes instance, the phylogram is plotted
            in that Axes. By default (None), a new figure is created.
        branch_labels : dict or callable
            A mapping of each clade to the label that will be shown along the
            branch leading to it. By default this is the confidence value(s) of
            the clade, taken from the ``confidence`` attribute, and can be
            easily toggled off with this function's ``show_confidence`` option.
            But if you would like to alter the formatting of confidence values,
            or label the branches with something other than confidence, then use
            this option.
        label_colors : dict or callable
            A function or a dictionary specifying the color of the tip label.
            If the tip label can't be found in the dict or label_colors is
            None, the label will be shown in black.
        orient_tree : string of 'horizontal', 'vertical' or 'circular'
            Whether the tree should be vertically oriented (default; i.e. leaves
            are plotted from top to bottom), horizontally oriented (i.e. leaves 
            are plotted from left to right) or a circular tree. Note that confidence
            labels will not be plotted on a circular tree.
        vertical_direction : string of 'left' or 'right'
            If the tree is vertical, whether the leaves should be on the left 
            (default) or the right.
        horizontal_direction : string of 'up' or 'down'
            If the tree is horizontal, whether the leaves should be on the bottom
            (default - down) or the top (up).
        circular_span : int or float between 0 and 365
            How much of a circle the circular plot should span. This value is in 
            degrees and is 355 (i.e. a small gap between the first and last leaf)
            by default.
        draw_labels : boolean
            Whether labels should be added to the tree (both branches and leaves).
            True by default.
        align_labels : boolean
            Whether leaf labels should be aligned so as they are all in the same 
            position and have a dotted line joining them. False by default.

    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        try:
            import pylab as plt
        except ImportError:
            raise MissingPythonDependencyError(
                "Install matplotlib or pylab if you want to use draw."
            ) from None

    import matplotlib.collections as mpcollections
    
    if orient_tree not in ["horizontal", "vertical", "circular"]:
        raise ValueError("orient_tree must be one of 'horizontal', 'vertical' or 'circular'")
    if orient_tree == "vertical" and vertical_direction not in ["right", "left"]:
        raise ValueError("vertical_direction must be one of 'right' or 'left'")
    elif orient_tree == "horizontal" and horizontal_direction not in ["up", "down"]:
        raise ValueError("horizontal_direction must be one of 'up' or 'down'")

    # Arrays that store lines for the plot of clades
    horizontal_linecollections = []
    vertical_linecollections = []

    # Options for displaying branch labels / confidence
    def conf2str(conf):
        if int(conf) == conf:
            return str(int(conf))
        return str(conf)

    if not branch_labels:
        if show_confidence:

            def format_branch_label(clade):
                try:
                    confidences = clade.confidences
                    # phyloXML supports multiple confidences
                except AttributeError:
                    pass
                else:
                    return "/".join(conf2str(cnf.value) for cnf in confidences)
                if clade.confidence is not None:
                    return conf2str(clade.confidence)
                return None

        else:

            def format_branch_label(clade):
                return None

    elif isinstance(branch_labels, dict):

        def format_branch_label(clade):
            return branch_labels.get(clade)

    else:
        if not callable(branch_labels):
            raise TypeError(
                "branch_labels must be either a dict or a callable (function)"
            )
        format_branch_label = branch_labels

    # options for displaying label colors.
    if label_colors:
        if callable(label_colors):

            def get_label_color(label):
                return label_colors(label)

        else:
            # label_colors is presumed to be a dict
            def get_label_color(label):
                return label_colors.get(label, "black")

    else:

        def get_label_color(label):
            # if label_colors is not specified, use black
            return "black"

    # Layout

    def get_x_positions(tree):
        """Create a mapping of each clade to its horizontal position.

        Dict of {clade: x-coord}
        """
        depths = tree.depths()
        # If there are no branch lengths, assume unit branch lengths
        if not max(depths.values()):
            depths = tree.depths(unit_branch_lengths=True)
        return depths

    def get_y_positions(tree):
        """Create a mapping of each clade to its vertical position.

        Dict of {clade: y-coord}.
        Coordinates are negative, and integers for tips.
        """
        maxheight = tree.count_terminals()
        # Rows are defined by the tips
        heights = {
            tip: maxheight - i for i, tip in enumerate(reversed(tree.get_terminals()))
        }

        # Internal nodes: place at midpoint of children
        def calc_row(clade):
            for subclade in clade:
                if subclade not in heights:
                    calc_row(subclade)
            # Closure over heights
            heights[clade] = (
                heights[clade.clades[0]] + heights[clade.clades[-1]]
            ) / 2.0

        if tree.root.clades:
            calc_row(tree.root)
        return heights

    x_posns = get_x_positions(tree)
    y_posns = get_y_positions(tree)
    # The function draw_clade closes over the axes object
    if axes is None:
        fig = plt.figure()
        axes = fig.add_subplot(1, 1, 1)
        if orient_tree == "circular":
            axes = fig.add_subplot(1, 1, 1, projection="polar")
            axes.yaxis.grid(False)
            axes.set_xticks([])
            axes.set_yticklabels([])
    elif orient_tree == "circular":
        if str(axes.name) != "polar":
            raise ValueError("Axes %s must have projection='polar' for a circular plot" % axes)
    elif not isinstance(axes, plt.matplotlib.axes.Axes):
        raise ValueError("Invalid argument for axes: %s" % axes)

    def draw_clade_lines(
        use_linecollection=False,
        orientation="horizontal",
        y_here=0,
        x_start=0,
        x_here=0,
        y_bot=0,
        y_top=0,
        color="black",
        lw=".1",
        linestyle="solid",
    ):
        """Create a line with or without a line collection object.

        Graphical formatting of the lines representing clades in the plot can be
        customized by altering this function.
        """
        if not use_linecollection and orientation == "horizontal":
            axes.hlines(y_here, x_start, x_here, color=color, lw=lw, linestyle=linestyle)
        elif use_linecollection and orientation == "horizontal":
            horizontal_linecollections.append(
                mpcollections.LineCollection(
                    [[(x_start, y_here), (x_here, y_here)]], color=color, lw=lw, linestyle=linestyle
                )
            )
        elif not use_linecollection and orientation == "vertical":
            axes.vlines(x_here, y_bot, y_top, color=color, linestyle=linestyle)
        elif use_linecollection and orientation == "vertical":
            vertical_linecollections.append(
                mpcollections.LineCollection(
                    [[(x_here, y_bot), (x_here, y_top)]], color=color, lw=lw, linestyle=linestyle
                )
            )

    def draw_clade(clade, x_start, color, lw):
        """Recursively draw a tree, down from the given clade."""
        x_here = x_posns[clade]
        y_here = y_posns[clade]
        xmax = max(x_posns.values())
        # phyloXML-only graphics annotations
        if hasattr(clade, "color") and clade.color is not None:
            color = clade.color.to_hex()
        if hasattr(clade, "width") and clade.width is not None:
            lw = clade.width * plt.rcParams["lines.linewidth"]
        # Draw a horizontal line from start to here
        if orient_tree == "vertical":
            draw_clade_lines(
                use_linecollection=True,
                orientation="horizontal",
                y_here=y_here,
                x_start=x_start,
                x_here=x_here,
                color=color,
                lw=lw,
            )
            #if this is one of the terminal branches and we want to align the 
            #labels then add a dashed line going from the end of the branch to
            #the start of the label
            if clade in tree.get_terminals() and align_labels:
                draw_clade_lines(
                    use_linecollection=True,
                    orientation="horizontal",
                    y_here=y_here,
                    x_start=x_here,
                    x_here=xmax,
                    color=color,
                    lw=lw-1,
                    linestyle="-.",
                )
            # Add node/taxon labels
            label = label_func(clade)
            if label not in (None, clade.__class__.__name__):
                if align_labels and clade in tree.get_terminals():
                    xplc = max(x_posns.values())+max(x_posns.values())/30
                else:
                    xplc = x_here
                if draw_labels:
                    if vertical_direction == "right":
                        va = "center"
                        ha = "left"
                    else:
                        va = "center"
                        ha = "right"
                    axes.text(
                        xplc,
                        y_here,
                        " %s" % label,
                        verticalalignment=va,
                        horizontalalignment=ha,
                        color=get_label_color(label),
                        )
            
            # Add label above the branch (optional)
            if draw_labels:
                conf_label = format_branch_label(clade)
                if conf_label:
                    axes.text(
                        0.5 * (x_start + x_here),
                        y_here,
                        conf_label,
                        fontsize="small",
                        horizontalalignment="center",
                    )
            if clade.clades:
                # Draw a vertical line connecting all children
                y_top = y_posns[clade.clades[0]]
                y_bot = y_posns[clade.clades[-1]]
                # Only apply widths to horizontal lines, like Archaeopteryx
                draw_clade_lines(
                    use_linecollection=True,
                    orientation="vertical",
                    x_here=x_here,
                    y_bot=y_bot,
                    y_top=y_top,
                    color=color,
                    lw=lw,
                )
                # Draw descendents
                for child in clade:
                    draw_clade(child, x_here, color, lw)
                    
        elif orient_tree == "horizontal":
            draw_clade_lines(
                use_linecollection=True,
                orientation="vertical", 
                x_here=y_here, 
                y_bot=x_start, 
                y_top=x_here,
                color=color,
                lw=lw,
            )
            #if this is one of the terminal branches and we want to align the 
            #labels then add a dashed line going from the end of the branch to
            #the start of the label
            if clade in tree.get_terminals() and align_labels:
                draw_clade_lines(
                    use_linecollection=True,
                    orientation="vertical", 
                    x_here=y_here, 
                    y_bot=x_here, 
                    y_top=xmax,
                    color=color,
                    lw=lw-1,
                    linestyle="-.",
                )
            # Add node/taxon labels
            label = label_func(clade)
            if label not in (None, clade.__class__.__name__):
                if align_labels and clade in tree.get_terminals():
                    xplc = max(x_posns.values())+max(x_posns.values())/30
                else:
                    xplc = x_here
                if draw_labels:
                    if horizontal_direction == "up":
                        va = "bottom"
                        ha = "center"
                    else:
                        va = "top"
                        ha = "center"
                    axes.text(
                        y_here, 
                        xplc,  
                        " %s" % label, 
                        verticalalignment=va, 
                        horizontalalignment=ha, 
                        color=get_label_color(label),
                        rotation=90
                        )
                    
            # Add label above the branch (optional)
            if draw_labels:
                conf_label = format_branch_label(clade)
                if conf_label:
                    axes.text(
                        0.5 * (y_posns[clade.clades[-1]] + y_here),
                        x_here,
                        conf_label,
                        fontsize="small",
                        horizontalalignment="center",
                    )
            if clade.clades:
                # Draw a vertical line connecting all children
                y_top = y_posns[clade.clades[0]]
                y_bot = y_posns[clade.clades[-1]]
                # Only apply widths to horizontal lines, like Archaeopteryx
                draw_clade_lines(
                    use_linecollection=True,
                    orientation="horizontal",
                    y_here=x_here,
                    x_start=y_bot,
                    x_here=y_top,
                    color=color,
                    lw=lw,
                )
                # Draw descendents
                for child in clade:
                    draw_clade(child, x_here, color, lw)
    
    
    def draw_clade_polar(clade, color, lw, x_start=0, y_start=0):
        
        try:
            import numpy as np
        except ImportError:
                raise MissingPythonDependencyError(
                    "Install numpy if you want to draw a circular tree."
                ) from None
        
        try:
            from scipy.interpolate import interp1d
        except ImportError:
                raise MissingPythonDependencyError(
                    "Install scipy if you want to draw a circular tree."
                ) from None
        
        #get the maximum y value and divide this by the circular span defined to give the angle that each y value is associated with
        ymax = max(y_posns.values())
        yang = circular_span/ymax
        xmax = max(x_posns.values())+max(x_posns.values())/30
        
        #convert the circular span from degrees to radians
        rad = (circular_span*np.pi/180)/ymax
    
        x_here = x_posns[clade]
        y_here = y_posns[clade]*rad
        
        #if x_here != 0: 
        axes.plot([y_start, y_here], [x_start, x_here], color=color, lw=lw)
        #if this is one of the terminal branches and we want to align the 
        #labels then add a dashed line going from the end of the branch to
        #the start of the label
        if clade in tree.get_terminals() and align_labels:
            axes.plot([y_start, y_here], [x_here, xmax], color=color, lw=lw-1, linestyle='-.')
        
        #plot the labels on branches and rotate them appropriately
        rot = y_here*(180/np.pi)
        label = label_func(clade)
        if clade.name not in (None, clade.__class__.__name__):
            if align_labels and clade in tree.get_terminals(): 
                xplc = xmax
            else: 
                xplc = x_here
            
            if rot <= 90: 
                va, ha = "center", "left"
            elif rot <= 180: 
                va, ha, rot = "center", "right", rot-180
            elif rot <= 270: 
                va, ha, rot = "center", "right", rot-180
            else: 
                va, ha = "center", "left"
            
            if draw_labels: 
                axes.text(y_here, xplc, label, color='k', rotation=rot, rotation_mode='anchor', va=va, ha=ha)
            

        if clade.clades:
            
            #multiply the y values by the angle needed and convert this to radians
            y_top = y_posns[clade.clades[0]]*yang*np.pi/180
            y_bot = y_posns[clade.clades[-1]]*yang*np.pi/180
            
            #plot a curve between this angle and the previous angle along the x axis
            curve = [[y_bot, y_top], [x_here, x_here]]
            
            x = np.linspace(curve[0][0], curve[0][1], 500)
            y = interp1d(curve[0], curve[1])(x)
            axes.plot(x, y, color=color, lw=lw)
            
            #calculate the distance between each branch coming from this x line
            ymin, ymax = min(x), max(x)
            ydiff = ymax-ymin
            c1 = [1 for child in clade]
            c1 = sum(c1)-2
            
            locs = [ymin]
            for a in range(c1):
                locs.append(ydiff/(c1+1)+ymin)
            locs.append(ymax)
            
            #plot the children, ensuring that they start on one of the x locations
            #along the branch that we've calculated
            count = 0
            for child in clade:
                if child in tree.get_terminals(): 
                    y_start = y_posns[child]*rad
                else:
                    y_start = locs[count]
                draw_clade_polar(child, color, lw, x_start=x_here, y_start=y_start)
                count += 1
        
        
        return
    
    if orient_tree in ["horizontal", "vertical"]:
        draw_clade(tree.root, 0, "k", plt.rcParams["lines.linewidth"])
        # If line collections were used to create clade lines, here they are added
        # to the pyplot plot.
        for i in horizontal_linecollections:
            axes.add_collection(i)
        for i in vertical_linecollections:
            axes.add_collection(i)
        
        if orient_tree == "vertical":
            axes.set_xlabel("branch length")
            axes.set_ylabel("taxa")
            # Add margins around the tree to prevent overlapping the axes
            # Also invert the y-axis (origin at the top)
            # Add a small vertical margin, but avoid including 0 and N+1 on the y axis
            axes.set_ylim(max(y_posns.values()) + 0.8, 0.2)
            xmax = max(x_posns.values())
            if vertical_direction == "right":
                axes.set_xlim(-0.05 * xmax, 1.25 * xmax)
            else:
                axes.set_xlim(1.25 * xmax, -0.05 * xmax)
        else:
            axes.set_ylabel("branch length")
            axes.set_xlabel("taxa")
            # Add margins around the tree to prevent overlapping the axes
            # Add a small horizontal margin, but avoid including 0 and N+1 on the y axis
            axes.set_xlim(max(y_posns.values()) + 0.8, 0.2)
            xmax = max(x_posns.values())
            if horizontal_direction == "down" and align_labels:
                axes.set_ylim(1.5 * xmax, -0.05 * xmax)
            elif horizontal_direction == "down":
                axes.set_ylim(1.25 * xmax, -0.05 * xmax)
            elif horizontal_direction == "up" and align_labels:
                axes.set_ylim(-0.05 * xmax, 1.6 * xmax)
            else:
                axes.set_ylim(-0.05 * xmax, 1.25 * xmax)
            
        
    elif orient_tree == "circular":
        draw_clade_polar(tree.root, "k", plt.rcParams["lines.linewidth"])
        xmax = max(x_posns.values())
        if draw_labels and align_labels:
            axes.set_ylim([0, 1.5*xmax])
        elif draw_labels:
            axes.set_ylim([0, 1.25*xmax])
        else:
            axes.set_ylim([0, xmax])


    # Aesthetics

    try:
        name = tree.name
    except AttributeError:
        pass
    else:
        if name:
            axes.set_title(name)
    

    # Parse and process key word arguments as pyplot options
    for key, value in kwargs.items():
        try:
            # Check that the pyplot option input is iterable, as required
            list(value)
        except TypeError:
            raise ValueError(
                'Keyword argument "%s=%s" is not in the format '
                "pyplot_option_name=(tuple), pyplot_option_name=(tuple, dict),"
                " or pyplot_option_name=(dict) " % (key, value)
            ) from None
        if isinstance(value, dict):
            getattr(plt, str(key))(**dict(value))
        elif not (isinstance(value[0], tuple)):
            getattr(plt, str(key))(*value)
        elif isinstance(value[0], tuple):
            getattr(plt, str(key))(*value[0], **dict(value[1]))

    if do_show:
        plt.show()
