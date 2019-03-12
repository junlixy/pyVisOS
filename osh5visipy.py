from __future__ import print_function
from functools import partial
from ipywidgets import interact, Layout, Output
import ipywidgets as widgets
from IPython.display import display, FileLink, clear_output

import numpy as np

import osh5vis
import osh5io
import glob
import os
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize, PowerNorm, SymLogNorm
import threading


print("Importing osh5visipy. Please use `%matplotlib notebook' in your jupyter/ipython notebook;")
print("use `%matplotlib widget' if you are using newer version of matplotlib (3.0) + jupyterlab (0.35)")


do_nothing = lambda x : x


def os2dplot_w(data, *args, pltfunc=osh5vis.osimshow, show=True, grid=None, **kwargs):
    """
    2D plot with widgets
    :param data: 2D H5Data
    :param args: arguments passed to 2d plotting widgets. reserved for future use
    :param show: whether to show the widgets
    :param kwargs: keyword arguments passed to 2d plotting widgets. reserved for future use
    :return: if show == True return None otherwise return a list of widgets
    """
    if isinstance(data, str):
        h5data = osh5io.read_h5(data)
        wl = Generic2DPlotCtrl(h5data, *args, pltfunc=pltfunc, **kwargs).widgets_list
    elif isinstance(data, (tuple, list)):
        if not grid:
            raise ValueError('Specify the grid layout when plotting more than one quantity!')
        if isinstance(data[0], str):
            data = [osh5io.read_h5(n) for n in data]
        wl = MultiPanelCtrl((Generic2DPlotCtrl,) * len(data), data, grid, **kwargs).widgets_list
    else:
        wl = Generic2DPlotCtrl(data, *args, pltfunc=pltfunc, **kwargs).widgets_list
    if show:
        display(*wl)
    else:
        return wl


osimshow_w = partial(os2dplot_w, pltfunc=osh5vis.osimshow)
oscontour_w = partial(os2dplot_w, pltfunc=osh5vis.oscontour)
oscontourf_w = partial(os2dplot_w, pltfunc=osh5vis.oscontourf)


def slicer_w(data, *args, show=True, slider_only=False, **kwargs):
    """
    A slider for 3D data
    :param data: 3D H5Data or directory name (a string)
    :param args: arguments passed to plotting widgets. reserved for future use
    :param show: whether to show the widgets
    :param slider_only: if True only show the slider otherwise show also other plot control (aka 'the tab')
    :param kwargs: keyword arguments passed to 2d plotting widgets. reserved for future use
    :return: whatever widgets that are not shown
    """
    if isinstance(data, str):
        wl = DirSlicer(data, *args, **kwargs).widgets_list
        tab, slider = wl[0], widgets.HBox(wl[1:-1])
    elif isinstance(data, (tuple, list)):
        if isinstance(data[0], str):
            wl = MPDirSlicer(data, *args, **kwargs).widgets_list
            tab, slider = wl[0], widgets.HBox(wl[1:-1])
    else:
        wl = Slicer(data, *args, **kwargs).widgets_list
        tab, slider = wl[0], widgets.HBox(wl[1:-1])
    if show:
        if slider_only:
            display(slider, wl[-1])
            return tab
        else:
            display(tab, slider, wl[-1])
    else:
        return wl


def animation_w(data, *args, **kwargs):
    wl = Animation(data, *args, **kwargs).widgets_list
    display(widgets.VBox([wl[0], widgets.HBox(wl[1:4]), widgets.HBox(wl[4:-2]), widgets.VBox(wl[-2:])]))


class Generic2DPlotCtrl(object):
    tab_contents = ['Data', 'Axes', 'Overlay', 'Colorbar', 'Save', 'Figure']
    eps = 1e-40
    colormaps_available = sorted(c for c in plt.colormaps() if not c.endswith("_r"))

    def __init__(self, data, pltfunc=osh5vis.osimshow, slcs=(slice(None, ), ), title=None, norm=None,
                 fig=None, figsize=None, time_in_title=True, ax=None, output_widget=None,
                 xlabel=None, ylabel=None, **kwargs):
        self._data, self._slcs, self.im_xlt, self.time_in_title, self.pltfunc = \
        data, slcs, None, time_in_title, pltfunc
        user_cmap, show_colorbar = kwargs.pop('cmap', 'jet'), kwargs.pop('colorbar', True)
        tab = []
        # # # -------------------- Tab0 --------------------------
        items_layout = Layout(flex='1 1 auto', width='auto')
        # title
        if not title:
            title = osh5vis.default_title(data, show_time=False)
        self.if_reset_title = widgets.Checkbox(value=True, description='Auto', layout=items_layout)
        self.datalabel = widgets.Text(value=title, placeholder='data', continuous_update=False,
                                     description='Data Name:', disabled=self.if_reset_title.value, layout=items_layout)
        self.if_show_time = widgets.Checkbox(value=time_in_title, description='Time in title', layout=items_layout)
        self._time = ''
        self.update_time_label()
        # normalization
        # general parameters: vmin, vmax, clip
        self.if_vmin_auto = widgets.Checkbox(value=True, description='Auto', layout=items_layout, style={'description_width': 'initial'})
        self.if_vmax_auto = widgets.Checkbox(value=True, description='Auto', layout=items_layout, style={'description_width': 'initial'})
        self.vmin_wgt = widgets.FloatText(value=np.min(data), description='vmin:', continuous_update=False,
                                          disabled=self.if_vmin_auto.value, layout=items_layout, style={'description_width': 'initial'})
        self.vlogmin_wgt = widgets.FloatText(value=self.eps, description='vmin:', continuous_update=False,
                                             disabled=self.if_vmin_auto.value, layout=items_layout, style={'description_width': 'initial'})
        self.vmax_wgt = widgets.FloatText(value=np.max(data), description='vmax:', continuous_update=False,
                                          disabled=self.if_vmin_auto.value, layout=items_layout, style={'description_width': 'initial'})
        self.if_clip_cm = widgets.Checkbox(value=True, description='Clip', layout=items_layout, style={'description_width': 'initial'})
        # PowerNorm specific
        self.gamma = widgets.FloatText(value=1, description='gamma:', continuous_update=False,
                                       layout=items_layout, style={'description_width': 'initial'})
        # SymLogNorm specific
        self.linthresh = widgets.FloatText(value=self.eps, description='linthresh:', continuous_update=False,
                                           layout=items_layout, style={'description_width': 'initial'})
        self.linscale = widgets.FloatText(value=1.0, description='linscale:', continuous_update=False,
                                          layout=items_layout, style={'description_width': 'initial'})

        # build the widgets tuple
        ln_wgt = (LogNorm, widgets.VBox([widgets.HBox([self.vmax_wgt, self.if_vmax_auto]),
                                         widgets.HBox([self.vlogmin_wgt, self.if_vmin_auto]), self.if_clip_cm]))
        n_wgt = (Normalize, widgets.VBox([widgets.HBox([self.vmax_wgt, self.if_vmax_auto]),
                                          widgets.HBox([self.vmin_wgt, self.if_vmin_auto]), self.if_clip_cm]))
        pn_wgt = (PowerNorm, widgets.VBox([widgets.HBox([self.vmax_wgt, self.if_vmax_auto]),
                                           widgets.HBox([self.vmin_wgt, self.if_vmin_auto]), self.if_clip_cm,
                                           self.gamma]))
        sln_wgt = (SymLogNorm, widgets.VBox(
            [widgets.HBox([self.vmax_wgt, self.if_vmax_auto]),
             widgets.HBox([self.vmin_wgt, self.if_vmin_auto]), self.if_clip_cm, self.linthresh, self.linscale]))

        # find out default value for norm_selector
        norm_avail = {'Log': ln_wgt, 'Normalize': n_wgt, 'Power': pn_wgt, 'SymLog': sln_wgt}
        self.norm_selector = widgets.Dropdown(options=norm_avail, style={'description_width': 'initial'},
                                              value=norm_avail.get(norm, n_wgt), description='Normalization:')
        self.__old_norm = self.norm_selector.value
        # additional care for LorNorm()
        self.__handle_lognorm()
        # re-plot button
        self.norm_btn_wgt = widgets.Button(description='Apply', disabled=False, tooltip='Update normalization', icon='refresh')
        tab.append(self.__get_tab0())

        # # # -------------------- Tab1 --------------------------
        self.setting_instructions = widgets.Label(value="Enter invalid value to reset", layout=items_layout)
        self.apply_range_btn = widgets.Button(description='Apply', disabled=False, tooltip='set range', icon='refresh')
        self.axis_lim_wgt = widgets.HBox([self.setting_instructions, self.apply_range_btn])
        # x axis
        xmin, xmax, xinc, ymin, ymax, yinc = self.__get_xy_minmax_delta()
        self.x_min_wgt = widgets.BoundedFloatText(value=xmin, min=xmin, max=xmax, step=xinc/2, description='xmin:',
                                                  continuous_update=False, layout=items_layout, style={'description_width': 'initial'})
        self.x_max_wgt = widgets.BoundedFloatText(value=xmax, min=xmin, max=xmax, step=xinc/2, description='xmax:',
                                                  continuous_update=False, layout=items_layout, style={'description_width': 'initial'})
        self.x_step_wgt = widgets.BoundedFloatText(value=xinc, step=xinc, continuous_update=False,
                                            description='$\Delta x$:', layout=items_layout, style={'description_width': 'initial'})
        widgets.jslink((self.x_min_wgt, 'max'), (self.x_max_wgt, 'value'))
        widgets.jslink((self.x_max_wgt, 'min'), (self.x_min_wgt, 'value'))
        # x label
        self.if_reset_xlabel = widgets.Checkbox(value=True, description='Auto', layout=items_layout, style={'description_width': 'initial'})
        if xlabel is False:
            self._xlabel = None
        elif isinstance(xlabel, str):
            self._xlabel = xlabel
        else:
            self._xlabel = osh5vis.axis_format(data.axes[1].long_name, data.axes[1].units)
        self.xlabel = widgets.Text(value=self._xlabel,
                                   placeholder='x', continuous_update=False,
                                   description='X label:', disabled=self.if_reset_xlabel.value)
        self.xaxis_lim_wgt = widgets.HBox([self.x_min_wgt, self.x_max_wgt, self.x_step_wgt, 
                                           widgets.HBox([self.xlabel, self.if_reset_xlabel], layout=Layout(border='solid 1px'))])
        # y axis
        self.y_min_wgt = widgets.BoundedFloatText(value=ymin, min=ymin, max=ymax, step=yinc/2, description='ymin:',
                                           continuous_update=False, layout=items_layout, style={'description_width': 'initial'})
        self.y_max_wgt = widgets.BoundedFloatText(value=ymax, min=ymin, max=ymax, step=yinc/2, description='ymax:',
                                           continuous_update=False, layout=items_layout, style={'description_width': 'initial'})
        self.y_step_wgt = widgets.BoundedFloatText(value=yinc, step=yinc, continuous_update=False,
                                            description='$\Delta y$:', layout=items_layout, style={'description_width': 'initial'})
        widgets.jslink((self.y_min_wgt, 'max'), (self.y_max_wgt, 'value'))
        widgets.jslink((self.y_max_wgt, 'min'), (self.y_min_wgt, 'value'))
        # y label
        self.if_reset_ylabel = widgets.Checkbox(value=True, description='Auto', layout=items_layout, style={'description_width': 'initial'})
        if ylabel is False:
            self._ylabel = None
        elif isinstance(ylabel, str):
            self._ylabel = ylabel
        else:
            self._ylabel = osh5vis.axis_format(data.axes[0].long_name, data.axes[0].units)
        self.ylabel = widgets.Text(value=self._ylabel,
                                   placeholder='y', continuous_update=False,
                                   description='Y label:', disabled=self.if_reset_ylabel.value)
        self.yaxis_lim_wgt = widgets.HBox([self.y_min_wgt, self.y_max_wgt, self.y_step_wgt,
                                           widgets.HBox([self.ylabel, self.if_reset_ylabel], layout=Layout(border='solid 1px'))])
        tab.append(widgets.VBox([self.axis_lim_wgt, self.xaxis_lim_wgt, self.yaxis_lim_wgt]))

        # # # -------------------- Tab2 --------------------------
        overlay_item_layout = Layout(display='flex', flex_flow='row wrap', width='auto')
        self.__analysis_def = {'Average': {'Simple': lambda x, a : np.mean(x, axis=a), 'RMS': lambda x, a : np.sqrt(np.mean(x*x, axis=a))},
                               'Sum': {'Simple': lambda x, a : np.sum(x, axis=a), 'Square': lambda x, a : np.sum(x*x, axis=a),
                                       'ABS': lambda x, a : np.sum(np.abs(x, axis=a))},
                               'Min': {'Simple': lambda x, a : np.min(x, axis=a), 'ABS': lambda x, a : np.min(np.abs(x), axis=a)},
                               'Max': {'Simple': lambda x, a : np.max(x, axis=a), 'ABS': lambda x, a : np.max(np.abs(x), axis=a)}} #TODO: envelope
        analist = [k for k in self.__analysis_def.keys()]
        # x lineout
        self.xlineout_wgt = widgets.BoundedFloatText(value=ymin, min=ymin, max=ymax, style={'description_width': 'initial'},
                                                     step=yinc, description=self.ylabel.value, layout={'width': 'initial'})
        widgets.jslink((self.xlineout_wgt, 'description'), (self.ylabel, 'value'))
        widgets.jslink((self.xlineout_wgt, 'min'), (self.y_min_wgt, 'value'))
        widgets.jslink((self.xlineout_wgt, 'max'), (self.y_max_wgt, 'value'))
        widgets.jslink((self.xlineout_wgt, 'step'), (self.y_step_wgt, 'value'))
        self.add_xlineout_btn = widgets.Button(description='Lineout', tooltip='Add x-lines', layout={'width': 'initial'})
        # simple analysis in x direction
        self.xananame = widgets.Dropdown(options=analist, value=analist[0], description='Analysis:',
                                         layout={'width': 'initial'}, style={'description_width': 'initial'})
        xanaoptlist = [k for k in self.__analysis_def[analist[0]].keys()]
        self.xanaopts = widgets.Dropdown(options=xanaoptlist, value=xanaoptlist[0], description='',
                                         layout={'width': 'initial'}, style={'description_width': 'initial'})
        self.anaxmin = widgets.BoundedFloatText(value=ymin, min=ymin, max=ymax, step=yinc, description='from',
                                                layout={'width': 'initial'}, style={'description_width': 'initial'})
        self.anaxmax = widgets.BoundedFloatText(value=ymax, min=ymin, max=ymax, step=yinc, description='to',
                                                layout={'width': 'initial'}, style={'description_width': 'initial'})
        widgets.jslink((self.anaxmin, 'min'), (self.y_min_wgt, 'value'))
        widgets.jslink((self.anaxmin, 'max'), (self.anaxmax, 'value'))
        widgets.jslink((self.anaxmin, 'step'), (self.y_step_wgt, 'value'))
        widgets.jslink((self.anaxmax, 'min'), (self.anaxmin, 'value'))
        widgets.jslink((self.anaxmax, 'max'), (self.y_max_wgt, 'value'))
        widgets.jslink((self.anaxmax, 'step'), (self.y_step_wgt, 'value'))
        self.xana_add = widgets.Button(description='Add', tooltip='Add analysis as x line plot', layout={'width': 'initial'})
        xlinegroup = widgets.HBox([self.xananame, self.xanaopts, self.anaxmin, self.anaxmax, self.xana_add], layout=Layout(border='solid 1px'))
        # list of x lines plotted
        self.xlineout_list_wgt = widgets.Box(children=[], layout=overlay_item_layout, style={'description_width': 'initial'})
        self.xlineout_tab = widgets.VBox([widgets.HBox([widgets.HBox([self.xlineout_wgt, self.add_xlineout_btn], 
                                                                     layout=Layout(border='solid 1px', flex='1 1 auto', width='auto')),
                                                        xlinegroup]), self.xlineout_list_wgt])
        # y lineout
        self.ylineout_wgt = widgets.BoundedFloatText(value=xmin, min=xmin, max=xmax, style={'description_width': 'initial'},
                                                     step=xinc, description=self.xlabel.value, layout={'width': 'initial'})
        widgets.jslink((self.ylineout_wgt, 'description'), (self.xlabel, 'value'))
        widgets.jslink((self.ylineout_wgt, 'min'), (self.x_min_wgt, 'value'))
        widgets.jslink((self.ylineout_wgt, 'max'), (self.x_max_wgt, 'value'))
        widgets.jslink((self.ylineout_wgt, 'step'), (self.x_step_wgt, 'value'))
        self.add_ylineout_btn = widgets.Button(description='Lineout', tooltip='Add y-lines', layout={'width': 'initial'})
        # simple analysis in x direction
        self.yananame = widgets.Dropdown(options=analist, value=analist[0], description='Analysis:',
                                         layout={'width': 'initial'}, style={'description_width': 'initial'})
        yanaoptlist = [k for k in self.__analysis_def[analist[0]].keys()]
        self.yanaopts = widgets.Dropdown(options=yanaoptlist, value=yanaoptlist[0], description='',
                                         layout={'width': 'initial'}, style={'description_width': 'initial'})
        self.anaymin = widgets.BoundedFloatText(value=xmin, min=xmin, max=xmax, step=xinc, description='from',
                                                layout={'width': 'initial'}, style={'description_width': 'initial'})
        self.anaymax = widgets.BoundedFloatText(value=xmax, min=xmin, max=xmax, step=xinc, description='to',
                                                layout={'width': 'initial'}, style={'description_width': 'initial'})
        widgets.jslink((self.anaymin, 'min'), (self.x_min_wgt, 'value'))
        widgets.jslink((self.anaymin, 'max'), (self.anaymax, 'value'))
        widgets.jslink((self.anaymin, 'step'), (self.x_step_wgt, 'value'))
        widgets.jslink((self.anaymax, 'min'), (self.anaymin, 'value'))
        widgets.jslink((self.anaymax, 'max'), (self.x_max_wgt, 'value'))
        widgets.jslink((self.anaymax, 'step'), (self.x_step_wgt, 'value'))
        self.yana_add = widgets.Button(description='Add', tooltip='Add analysis as y line plot', layout={'width': 'initial'})
        ylinegroup = widgets.HBox([self.yananame, self.yanaopts, self.anaymin, self.anaymax, self.yana_add],
                                  layout=Layout(width='initial', border='solid 1px'))
        # list of x lines plotted
        self.ylineout_list_wgt = widgets.Box(children=[], layout=overlay_item_layout)
        self.ylineout_tab = widgets.VBox([widgets.HBox([widgets.HBox([self.ylineout_wgt, self.add_ylineout_btn], 
                                                                     layout=Layout(border='solid 1px', flex='1 1 auto', width='auto')),
                                                        ylinegroup]), self.ylineout_list_wgt])
        #TODO: overlay 2D plot

        self.overlaid_itmes = {}  # dict to keep track of the overlaid plots
        self.overlay = widgets.Tab(children=[self.xlineout_tab, self.ylineout_tab])
        [self.overlay.set_title(i, tt) for i, tt in enumerate(['x-line', 'y-line'])]
        tab.append(self.overlay)

        # # # -------------------- Tab3 --------------------------
        self.colorbar = widgets.Checkbox(value=show_colorbar, description='Show colorbar')
        self.cmap_selector = widgets.Dropdown(options=self.colormaps_available, value=user_cmap,
                                              description='Colormap:', disabled=not show_colorbar)
        self.cmap_reverse = widgets.Checkbox(value=False, description='Reverse', disabled=not show_colorbar)
        # colorbar
        self.if_reset_cbar = widgets.Checkbox(value=True, description='Auto', disabled=not show_colorbar)
        self.cbar = widgets.Text(value=data.units.tex(), placeholder='a.u.', continuous_update=False,
                                 description='Colorbar:', disabled=self.if_reset_cbar.value or not show_colorbar)
        tab.append(widgets.VBox([self.colorbar,
                                 widgets.HBox([self.cmap_selector, self.cmap_reverse], layout=items_layout),
                                 widgets.HBox([self.cbar, self.if_reset_cbar])], layout=items_layout))

        # # # -------------------- Tab4 --------------------------
        self.saveas = widgets.Button(description='Save current plot', tooltip='save current plot', button_style='')
        self.dlink = Output()
        self.figname = widgets.Text(value='figure.eps', description='Filename:')
        self.dpi = widgets.BoundedIntText(value=300, min=4, max=3000, description='DPI:')
        tab.append(widgets.VBox([widgets.HBox([self.figname, self.dpi], layout=items_layout),
                                 self.saveas, self.dlink], layout=items_layout))

        # # # -------------------- Tab5 --------------------------
        width, height = figsize or plt.rcParams.get('figure.figsize')
        self.figwidth = widgets.BoundedFloatText(value=width, min=0.1, step=0.01, description='Width:')
        self.figheight = widgets.BoundedFloatText(value=height, min=0.1, step=0.01, description='Height:')
        self.resize_btn = widgets.Button(description='Adjust figure', tooltip='Update figure', icon='refresh')
        tab.append(widgets.HBox([self.figwidth, self.figheight, self.resize_btn], layout=items_layout))

        # construct the tab
        self.tab = widgets.Tab()
        self.tab.children = tab
        [self.tab.set_title(i, tt) for i, tt in enumerate(self.tab_contents)]


        # link and activate the widgets
        self.if_reset_title.observe(self.__update_title, 'value')
        self.if_reset_xlabel.observe(self.__update_xlabel, 'value')
        self.if_reset_ylabel.observe(self.__update_ylabel, 'value')
        self.if_reset_cbar.observe(self.__update_cbar, 'value')
        self.norm_btn_wgt.on_click(self.update_norm)
        self.if_vmin_auto.observe(self.__update_vmin, 'value')
        self.if_vmax_auto.observe(self.__update_vmax, 'value')
        self.norm_selector.observe(self.__update_norm_wgt, 'value')
        self.cmap_selector.observe(self.update_cmap, 'value')
        self.cmap_reverse.observe(self.update_cmap, 'value')
        self.datalabel.observe(self.update_title, 'value')
        self.if_show_time.observe(self.update_title, 'value')
        self.xlabel.observe(self.update_xlabel, 'value')
        self.ylabel.observe(self.update_ylabel, 'value')
        self.cbar.observe(self.update_cbar, 'value')
        self.apply_range_btn.on_click(self.update_plot_area)
        self.figname.observe(self.__reset_save_button, 'value')
        self.saveas.on_click(self.__try_savefig)
        self.colorbar.observe(self.__toggle_colorbar, 'value')
        self.resize_btn.on_click(self.adjust_figure)
        self.add_xlineout_btn.on_click(self.__add_xlineout)
        self.add_ylineout_btn.on_click(self.__add_ylineout)
        self.xananame.observe(self.__update_xanaopts, 'value')
        self.xana_add.on_click(self.__add_xana)
        self.yananame.observe(self.__update_yanaopts, 'value')
        self.yana_add.on_click(self.__add_yana)

        # plotting and then setting normalization colors
        self.out_main = output_widget or Output()
        self.observer_thrd, self.cb = None, None
        self.fig = fig or plt.figure(figsize=[width, height], constrained_layout=True)
        self.ax = ax or self.fig.add_subplot(111)
        with self.out_main:
            self.im, self.cb = self.plot_data()
#             plt.show()
        self.axx, self.axy, self._xlineouts, self._ylineouts = None, None, {}, {}

    @property
    def widgets_list(self):
        return self.tab, self.out_main

    @property
    def widget(self):
        return widgets.VBox([self.tab, self.out_main])

    def get_dataname(self):
        return self._data.name

    def get_time_label(self):
        return osh5vis.time_format(self._data.run_attrs['TIME'][0], self._data.run_attrs['TIME UNITS'])

    def update_data(self, data, slcs):
        self._data, self._slcs = data, slcs
        self.__update_title()
        self.__update_xlabel()
        self.__update_ylabel()

    def reset_plot_area(self):
        self.x_min_wgt.value, self.x_max_wgt.value, xstep, \
        self.y_min_wgt.value, self.y_max_wgt.value, ystep = self.__get_xy_minmax_delta()
        self.x_step_wgt.value, self.y_step_wgt.value = xstep / 2, ystep / 2
        self.__destroy_all_xlineout()
        self.__destroy_all_ylineout()

    def redraw(self, data):
        if self.pltfunc is osh5vis.osimshow:
            "if the size of the data is the same we can just redraw part of figure"
            self._data = data
            self.im.set_data(self.__pp(data[self._slcs]))
            self.fig.canvas.draw()
        else:
            "for contour/contourf we have to do a full replot"
            self._data = data
            for col in self.im.collections:
                col.remove()
            self.replot_axes()

    def update_title(self, *_):
        self.ax.axes.set_title(self.__get_plot_title())

    def update_xlabel(self, change):
        self.ax.axes.xaxis.set_label_text(change['new'])

    def update_ylabel(self, change):
        self.ax.axes.yaxis.set_label_text(change['new'])

    def update_cbar(self, change):
        self.im.colorbar.set_label(change['new'])

    def update_cmap(self, _change):
        cmap = self.cmap_selector.value if not self.cmap_reverse.value else self.cmap_selector.value + '_r'
        self.im.set_cmap(cmap)
        self.cb.set_cmap(cmap)

    def update_time_label(self):
        self._time = osh5vis.time_format(self._data.run_attrs['TIME'][0], self._data.run_attrs['TIME UNITS'])

    def adjust_figure(self, *_):
        with self.out_main:
            self.out_main.clear_output(wait=True)
            # this dosen't work in all scenarios. it could be a bug in matplotlib/jupyterlab
            self.fig.set_size_inches(self.figwidth.value, self.figheight.value)

    def replot_axes(self):
#         self.fig.delaxes(self.ax)
# #         self.fig.clear()
#         self.ax = self.fig.add_subplot(111)
        self.ax.cla()
#         self.im.remove()
        self.im, cb = self.plot_data(colorbar=self.colorbar.value)
        if self.colorbar.value:
            self.cb.remove()
            self.cb = cb
#         self.fig.subplots_adjust()  # does not compatible with constrained_layout in Matplotlib 3.0

    def __get_xy_minmax_delta(self):
        return (round(self._data.axes[1].min, 2), round(self._data.axes[1].max, 2), round(self._data.axes[1].increment, 2),
                round(self._data.axes[0].min, 2), round(self._data.axes[0].max, 2), round(self._data.axes[0].increment, 2))

    def update_plot_area(self, *_):
        bnd = [(self.y_min_wgt.value, self.y_max_wgt.value, self.y_step_wgt.value),
               (self.x_min_wgt.value, self.x_max_wgt.value, self.x_step_wgt.value)]
        self._slcs = tuple(slice(*self._data.get_index_slice(self._data.axes[i], bd)) for i, bd in enumerate(bnd))
        #TODO: maybe we can keep some of the overlaid plots but replot_axes will generate new axes.
        # for now delete everything for simplicity
        self.__destroy_all_xlineout()
        self.__destroy_all_ylineout()
        self.replot_axes()

    def refresh_tab_wgt(self, update_list):
        """
        the tab.children is a tuple so we have to reconstruct the whole tab widget when
        addition/deletion of children widgets happens
        """
        tmp = self.tab.children
        newtab = [tmp[i] if not t else t for i, t in enumerate(update_list)]
        self.tab.children = tuple(newtab)

    def plot_data(self, **passthrough):
        ifcolorbar = passthrough.pop('colorbar', self.colorbar.value)
        return self.pltfunc(self.__pp(self._data[self._slcs]), cmap=self.cmap_selector.value,
                            norm=self.norm_selector.value[0](**self.__get_norm()), title=self.__get_plot_title(),
                            xlabel=self.xlabel.value, ylabel=self.ylabel.value, cblabel=self.cbar.value,
                            ax=self.ax, fig=self.fig, colorbar=ifcolorbar, **passthrough)
    
    def __get_plot_title(self):
        if self.datalabel.value:
            return self.datalabel.value + ((', ' + self._time) if self.if_show_time.value else '')
        else:
            return self._time if self.if_show_time.value else ''

    def __get_tab0(self):
        return widgets.HBox([widgets.VBox([self.norm_selector, self.norm_selector.value[1]]), self.norm_btn_wgt,
                             widgets.VBox([widgets.HBox([self.datalabel, self.if_reset_title]), self.if_show_time])])

    def __update_xanaopts(self, change):
        opts = self.__analysis_def[change['new']]
        optlist = [k for k in opts.keys()]
        self.xanaopts.options, self.xanaopts.value = optlist, optlist[0]

    def __add_xana(self, change):
        start, end = self._data[self._slcs].loc.label2int(0, self.anaxmin.value), self._data[self._slcs].loc.label2int(0, self.anaxmax.value)
        if start < end:
            fn =self.__analysis_def[self.xananame.value][self.xanaopts.value]
            data, posstr = (self.__pp(fn(self._data[self._slcs][start:end, :], 0)),
                            '%.2f ~ %.2f' % (self._data[self._slcs].axes[0][start], self._data[self._slcs].axes[0][end]))
            tp = posstr + ' ' + self.xanaopts.value + ' ' + self.xananame.value
        self.__add_xline(data, posstr, tp, 240)

    def __update_yanaopts(self, change):
        opts = self.__analysis_def[change['new']]
        optlist = [k for k in opts[1].keys()]
        self.yanaopts.options, self.yanaopts.value = optlist, optlist[0]

    def __add_yana(self, change):
        start, end = self._data[self._slcs].loc.label2int(1, self.anaymin.value), self._data[self._slcs].loc.label2int(1, self.anaymax.value)
        if start < end:
            fn = self.__analysis_def[self.yananame.value][self.yanaopts.value]
            data, posstr = (self.__pp(fn(self._data[self._slcs][:, start:end], 1)),
                             '%.2f ~ %.2f' % (self._data[self._slcs].axes[1][start], self._data[self._slcs].axes[1][end]))
            tp = posstr + ' ' + self.yanaopts.value + ' ' + self.yananame.value
        self.__add_yline(data, posstr, tp, 240)

    def __update_twinx_scale(self):
        if self.norm_selector.value[0] == LogNorm:
            self.axx.set_yscale('log')
        elif self.norm_selector.value[0] == SymLogNorm:
            self.axx.set_yscale('symlog')
        else:
            self.axx.set_yscale('linear')

    def __destroy_all_xlineout(self):
        if self._xlineouts:
            for li in self.xlineout_list_wgt.children:
                # remove lineout
                self._xlineouts[li.children[0]].remove()
                # remove widget
                li.close()
            # unregister all widgets
            self._xlineouts = {}
            self.xlineout_list_wgt.children = tuple()
            # remove axes
            self.axx.remove()

    def __remove_xlineout(self, btn):
        # unregister widget
        xlineout_wgt = self._xlineouts.pop(btn)
        xlineout = self._xlineouts.pop(xlineout_wgt.children[0])
        # remove x lineout
        xlineout.remove()
        # remove x lineout item widgets
        tmp = list(self.xlineout_list_wgt.children)
        tmp.remove(xlineout_wgt)
        self.xlineout_list_wgt.children = tuple(tmp)
        xlineout_wgt.close()
        # remove axes if all lineout is deleted
        if not self._xlineouts:
            self.axx.remove()
#         #TODO: a walkaround for a strange behavior of constrained_layout

    def __set_xlineout_color(self, color):
        self._xlineouts[color['owner']].set_color(color['new'])

    def __add_xline(self, data, descr, tp, wgt_width):
        # add twinx if not exist
        if not self._xlineouts:
            self.axx = self.ax.twinx()
            self.__update_twinx_scale()
        # plot
        xlineout = osh5vis.osplot1d(data, ax=self.axx, xlabel='', ylabel='', title='')[0]
        # add widgets (color picker + delete button)
        nw = widgets.Button(description='', tooltip='delete %s' % tp, icon='times', layout=Layout(width='32px'))
        nw.on_click(self.__remove_xlineout)
        co = xlineout.get_color()
        cpk = widgets.ColorPicker(concise=False, description=descr, value=co, style={'description_width': 'initial'},
                                  layout=Layout(width='%dpx' % wgt_width))
        cpk.observe(self.__set_xlineout_color, 'value')
        lineout_wgt = widgets.HBox([cpk, nw], layout=Layout(width='%dpx' % (wgt_width + 50), border='solid 1px', flex='0 0 auto'))
        self.xlineout_list_wgt.children += (lineout_wgt,)
        # register a new lineout
        self._xlineouts[nw], self._xlineouts[cpk] = lineout_wgt, xlineout

    def __add_xlineout(self, *_):
        pos = self._data[self._slcs].loc.label2int(0, self.xlineout_wgt.value)
        # plot
        data, posstr = self.__pp(self._data[self._slcs][pos, :]), '%.2f' % self._data.axes[0][pos]
        tp = posstr + ' lineout'
        self.__add_xline(data, posstr, tp, 170)

    def __update_xlineout(self):
        if self._xlineouts:
#             for k, v in self._xlineouts.items():
#                 if hasattr(v, 'set_ydata'):
#                     v.set_ydata(self.__pp(v.get_ydata()))
#             for wgt in self.xlineout_list_wgt.children:
#                 pos = float(wgt.children[0].description)
#                 self._xlineouts[wgt.children[0]].set_ydata(self.__pp(self._data[self._slcs].loc[pos, :]))
            self.__update_twinx_scale()
            #TODO: autoscale for 'log' scale doesn't work after plotting the line, we have to do it manually
            #TDDO: a walkaround for a strange behavior of constrained_layout, should be removed in the future
            self.axx.set_ylabel('')

    def __update_twiny_scale(self):
        if self.norm_selector.value[0] == LogNorm:
            self.axy.set_xscale('log')
        elif self.norm_selector.value[0] == SymLogNorm:
            self.axy.set_xscale('symlog')
        else:
            self.axy.set_xscale('linear')

    def __destroy_all_ylineout(self):
        if self._ylineouts:
            for li in self.ylineout_list_wgt.children:
                # remove lineout
                self._ylineouts[li.children[0]].remove()
                # remove widget
                li.close()
            # unregister all widgets
            self._ylineouts = {}
            self.ylineout_list_wgt.children = tuple()
            # remove axes
            self.axy.remove()

    def __remove_ylineout(self, btn):
        # unregister widget
        ylineout_wgt = self._ylineouts.pop(btn)
        ylineout = self._ylineouts.pop(ylineout_wgt.children[0])
        # remove x lineout
        ylineout.remove()
        # remove x lineout item widgets
        tmp = list(self.ylineout_list_wgt.children)
        tmp.remove(ylineout_wgt)
        self.ylineout_list_wgt.children = tuple(tmp)
        ylineout_wgt.close()
        # remove axes if all lineout is deleted
        if not self._ylineouts:
            self.axy.remove()

    def __set_ylineout_color(self, color):
        self._ylineouts[color['owner']].set_color(color['new'])

    def __add_yline(self, data, descr, tp, wgt_width):
        # add twinx if not exist
        if not self._ylineouts:
            self.axy = self.ax.twiny()
            self.__update_twiny_scale()
        # plot
        ylineout = osh5vis.osplot1d(data, ax=self.axy, xlabel='', ylabel='', title='', transpose=True)[0]
        # add widgets (color picker + delete button)
        nw = widgets.Button(description='', tooltip='delete %s' % tp, icon='times', layout=Layout(width='32px'))
        nw.on_click(self.__remove_ylineout)
        co = ylineout.get_color()
        cpk = widgets.ColorPicker(concise=False, description=descr, value=co, style={'description_width': 'initial'},
                                  layout=Layout(width='%dpx' % wgt_width))
        cpk.observe(self.__set_ylineout_color, 'value')
        lineout_wgt = widgets.HBox([cpk, nw], layout=Layout(width='%dpx' % (wgt_width + 50), border='solid 1px', flex='0 0 auto'))
        self.ylineout_list_wgt.children += (lineout_wgt,)
        # register a new lineout
        self._ylineouts[nw], self._ylineouts[cpk] = lineout_wgt, ylineout

    def __add_ylineout(self, *_):
        pos = self._data.loc.label2int(1, self.ylineout_wgt.value)
        # plot
        data, posstr = self.__pp(self._data[self._slcs][:, pos]), '%.2f' % self._data.axes[1][pos]
        tp = posstr + ' lineout'
        self.__add_yline(data, posstr, tp, 170)

    def __update_ylineout(self):
        if self._ylineouts:
#             for wgt in self.ylineout_list_wgt.children:
#                 pos = float(wgt.children[0].description)
#                 self._ylineouts[wgt.children[0]].set_xdata(self.__pp(self._data[self._slcs].loc[:, pos]))
            self.__update_twiny_scale()
            #TODO: autoscale for 'log' scale doesn't work after plotting the line, we have to do it manually
            #TDDO: a walkaround for a strange behavior of constrained_layout, should be removed in the future
            self.axy.set_ylabel('')

    def __handle_lognorm(self):
        s = self._data.shape
        dx, dy = 10 if s[1] > 200 else 1, 10 if s[0] > 200 else 1
        v = self._data.values[::dy, ::dx]
        if self.norm_selector.value[0] == LogNorm:
            self.__pp = np.abs
            self.vlogmin_wgt.value, self.vmax_wgt.value = np.min(np.abs(v[v!=0])), np.max(np.abs(v))
#             vmin, _ = self.__get_vminmax()
#             self.__assgin_valid_vmin(v=vmin)
        else:
            self.vmin_wgt.value, self.vmax_wgt.value = np.min(v), np.max(v)
#             self.__assgin_valid_vmin()
            self.__pp = do_nothing

    def __update_norm_wgt(self, change):
        """update tab1 (second tab) only and prepare _log_data if necessary"""
        tmp = [None] * len(self.tab_contents)
        tmp[0] = self.__get_tab0()
        self.refresh_tab_wgt(tmp)
        self.__handle_lognorm()
        self.__old_norm = change['old']

    def __get_vminmax(self, from_widgets=False):
        if from_widgets:
            return self.norm_selector.value[1].children[1].children[0].value, self.vmax_wgt.value
        else:
            return (None if self.if_vmin_auto.value else self.norm_selector.value[1].children[1].children[0].value,
                    None if self.if_vmax_auto.value else self.vmax_wgt.value)

    def __axis_descr_format(self, comp):
        return osh5vis.axis_format(self._data.axes[comp].long_name, self._data.axes[comp].units)

    def update_norm(self, *args):
        # only changing clim
        if self.__old_norm == self.norm_selector.value:
            vmin, vmax = self.__get_vminmax(from_widgets=True)
            self.im.set_clim([vmin, vmax])
        # norm change
        else:
            vminmax = self.__get_vminmax()
            self.__update_xlineout()
            self.__update_ylineout()
            self.im.remove()
            if self.colorbar.value:
                self.im, cb = self.plot_data()
                self.cb.ax.remove()
                self.cb = cb
            else:
                self.im, _ = self.plot_data(colorbar=False)

    def __get_norm(self, vminmax_from_wiget=False):
        vmin, vmax = self.__get_vminmax(vminmax_from_wiget)
        param = {'vmin': vmin, 'vmax': vmax, 'clip': self.if_clip_cm.value}
        if self.norm_selector.value[0] == PowerNorm:
            param['gamma'] = self.gamma.value
        if self.norm_selector.value[0] == SymLogNorm:
            param['linthresh'] = self.linthresh.value
            param['linscale'] = self.linscale.value
        return param

    def __assgin_valid_vmin(self, v=None):
        # if it is log scale
        if self.norm_selector.value[0] == LogNorm:
            self.vlogmin_wgt.value = self.eps if v is None or v < self.eps else v
        else:
            self.vmin_wgt.value = np.min(self._data) if v is None else v

    def __add_colorbar(self):
        clb = self.cbar.value
        self.cb = osh5vis.add_colorbar(self.im, fig=self.fig, ax=self.ax, cblabel=clb)

    def __toggle_colorbar(self, change):
        if change['new']:
            self.cbar.disabled, self.if_reset_cbar.disabled, self.cmap_selector.disabled, \
            self.cmap_reverse.disabled = False, False, False, False
            self.__update_cbar(change)
            self.__add_colorbar()
        else:
            self.cbar.disabled, self.if_reset_cbar.disabled, self.cmap_selector.disabled, \
            self.cmap_reverse.disabled = True, True, True, True
            self.cb.remove()
#         self.replot_axes()

    def __update_vmin(self, _change):
        if self.if_vmin_auto.value:
            self.__assgin_valid_vmin()
            self.vmin_wgt.disabled = True
            self.vlogmin_wgt.disabled = True
        else:
            self.vmin_wgt.disabled = False
            self.vlogmin_wgt.disabled = False

    def __update_vmax(self, _change):
        if self.if_vmax_auto.value:
            self.vmax_wgt.value = np.max(self._data)
            self.vmax_wgt.disabled = True
        else:
            self.vmax_wgt.disabled = False

    def __update_title(self, *_):
        if self.if_reset_title.value:
            self.datalabel.value = osh5vis.default_title(self._data, show_time=False)
            self.datalabel.disabled = True
        else:
            self.datalabel.disabled = False

    def __update_xlabel(self, *_):
        if self.if_reset_xlabel.value:
            self.xlabel.value = self._xlabel
            self.xlabel.disabled = True
        else:
            self.xlabel.disabled = False

    def __update_ylabel(self, *_):
        if self.if_reset_ylabel.value:
            self.ylabel.value = self._ylabel
            self.ylabel.disabled = True
        else:
            self.ylabel.disabled = False

    def __update_cbar(self, *_):
        if self.if_reset_cbar.value:
            self.cbar.value = self._data.units.tex()
            self.cbar.disabled = True
        else:
            self.cbar.disabled = False

    def __reset_save_button(self, *_):
        self.saveas.description, self.saveas.tooltip, self.saveas.button_style= \
        'Save current plot', 'save current plot', ''

    def __savefig(self):
        try:
            self.fig.savefig(self.figname.value, dpi=self.dpi.value)
#             self.dlink.clear_output(wait=True)
            with self.dlink:
                clear_output(wait=True)
                print('shift+right_click to downloaod:')
                display(FileLink(self.figname.value))
            self.__reset_save_button(0)
        except PermissionError:
            self.saveas.description, self.saveas.tooltip, self.saveas.button_style= \
                    'Permission Denied', 'please try another directory', 'danger'

    def __try_savefig(self, *_):
        pdir = os.path.abspath(os.path.dirname(self.figname.value))
        path_exist = os.path.exists(pdir)
        file_exist = os.path.exists(self.figname.value)
        if path_exist:
            if file_exist:
                if not self.saveas.button_style:
                    self.saveas.description, self.saveas.tooltip, self.saveas.button_style= \
                    'Overwirte file', 'overwrite existing file', 'warning'
                else:
                    self.__savefig()
            else:
                self.__savefig()
        else:
            if not self.saveas.button_style:
                self.saveas.description, self.saveas.tooltip, self.saveas.button_style= \
                'Create path & save', 'create non-existing path and save', 'warning'
            else:
                os.makedirs(pdir)
                self.__savefig()


class Slicer(Generic2DPlotCtrl):
    def __init__(self, data, d=0, **extra_kwargs):
        if np.ndim(data) != 3:
            raise ValueError('data must be 3 dimensional')
        self.x, self.comp, self.data = data.shape[d] // 2, d, data
        self.slcs = self.__get_slice(d)
        self.axis_pos = widgets.FloatText(value=data.axes[self.comp][self.x],
                                          description=self.__axis_format(), continuous_update=False)
        self.index_slider = widgets.IntSlider(min=0, max=self.data.shape[self.comp] - 1, step=1, description='index:',
                                              value=self.data.shape[self.comp] // 2, continuous_update=False)

        self.axis_selector = widgets.Dropdown(options=list(range(data.ndim)), value=self.comp, description='axis:')
        self.axis_selector.observe(self.switch_slice_direction, 'value')
        self.index_slider.observe(self.update_slice, 'value')
        self.axis_pos.observe(self.__update_index_slider, 'value')

        super(Slicer, self).__init__(data[self.slcs], slcs=[i for i in self.slcs if not isinstance(i, int)],
                                     time_in_title=not data.has_axis('t'), **extra_kwargs)

    @property
    def widgets_list(self):
        return self.tab, self.axis_pos, self.index_slider, self.axis_selector, self.out_main

    @property
    def widget(self):
        return widgets.VBox([widgets.HBox([self.axis_pos, self.index_slider, self.axis_selector]),
                             self.out_main])

    def __update_index_slider(self, _change):
        self.index_slider.value = round((self.axis_pos.value - self.data.axes[self.comp].min)
                                        / self.data.axes[self.comp].increment)

    def __axis_format(self):
        return osh5vis.axis_format(self.data.axes[self.comp].long_name, self.data.axes[self.comp].units)

    def __get_slice(self, c):
        slcs = [slice(None)] * self.data.ndim
        slcs[c] = self.data.shape[c] // 2
        return slcs

    def switch_slice_direction(self, change):
        self.slcs, self.comp, self.x = \
            self.__get_slice(change['new']), change['new'], self.data.shape[change['new']] // 2
        self.reset_slider_index()
        self.__update_axis_descr()
        self.update_data(self.data[self.slcs], slcs=[i for i in self.slcs if not isinstance(i, int)])
        self.reset_plot_area()
        self.replot_axes()

    def reset_slider_index(self):
        # stop the observe while updating values
        self.index_slider.unobserve(self.update_slice, 'value')
        self.index_slider.max = self.data.shape[self.comp] - 1
        self.__update_axis_value()
        self.index_slider.observe(self.update_slice, 'value')

    def __update_axis_value(self, *_):
        self.axis_pos.value = str(self.data.axes[self.comp][self.x])

    def __update_axis_descr(self, *_):
        self.axis_pos.description = self.__axis_format()

    def update_slice(self, index):
        self.x = index['new']
        self.__update_axis_value()
        self.slcs[self.comp] = self.x
        self.redraw(self.data[self.slcs])


class DirSlicer(Generic2DPlotCtrl):
    def __init__(self, filefilter, processing=do_nothing, **extra_kwargs):
        fp = filefilter + '/*.h5' if os.path.isdir(filefilter) else filefilter
        self.datadir, self.flist, self.processing = os.path.abspath(os.path.dirname(fp)), sorted(glob.glob(fp)), processing
        try:
            self.data = processing(osh5io.read_h5(self.flist[0]))
        except IndexError:
            raise IOError('No file found matching ' + fp)

        items_layout = Layout(flex='1 1 auto', width='auto')
        self.file_slider = widgets.IntSlider(min=0, max=len(self.flist), description=os.path.basename(self.flist[0]), 
                                             value=0, readout=False, continuous_update=False, layout=items_layout,
                                             style={'description_width': 'initial'})
        self.time_label = widgets.Label(value=osh5vis.time_format(self.data.run_attrs['TIME'][0], self.data.run_attrs['TIME UNITS']),
                                        layout=items_layout)
        self.file_slider.observe(self.update_slice, 'value')

        super(DirSlicer, self).__init__(self.data, time_in_title=False, **extra_kwargs)


    @property
    def widgets_list(self):
        return self.tab, self.file_slider, self.time_label, self.out_main

    @property
    def widget(self):
        return widgets.VBox([widgets.HBox[self.file_slider, self.time_label], self.out_main])

    def update_slice(self, change):
        self.file_slider.description = os.path.basename(self.flist[change['new']])
        self.data = self.processing(osh5io.read_h5(self.flist[change['new']]))
        self.time_label.value = osh5vis.time_format(self.data.run_attrs['TIME'][0], self.data.run_attrs['TIME UNITS'])
        self.redraw(self.data)
        if self.if_show_time:
            self.update_time_label()
            self.update_title(change)


class MultiPanelCtrl(object):
    def __init__(self, workers, data_list, grid, worker_kw_list=None, figsize=None, fig=None, output_widget=None,
                 sharex=False, sharey=False, **kwargs):
        """ worker's base class should be Generic2DPlotCtrl """
        if len(grid) != 2 or np.multiply(*grid) <= 1:
            raise ValueError('grid must have 2 elements specifying a grid of plots. Total number of plots must be greater than 1')
        self.nrows, self.ncols = grid
        if len(data_list) != self.nrows * self.ncols:
            raise ValueError('Expecting %d lists in data_list, got %d' % (self.nrows * self.ncols, len(data_list)))
        
        width, height = figsize or plt.rcParams.get('figure.figsize')
        self.out = output_widget or widgets.Output()
        nplots = self.nrows * self.ncols
        xlabel, ylabel = [None,] * nplots, [None,] * nplots
        if str(sharex).lower() in ('true', 'all', 'col'):
            for i in range(nplots - self.ncols):
                xlabel[i] = False
        if str(sharey).lower() in ('true', 'all', 'row'):
            for i in range(nplots):
                if i % self.ncols != 0:
                    ylabel[i] = False
        if worker_kw_list is None:
            worker_kw_list = ({}, ) * nplots
        self.fig, self.ax = plt.subplots(self.nrows, self.ncols, figsize=(width, height), 
                                         sharex=sharex, sharey=sharey, constrained_layout=True)
        self.worker = [w(d, output_widget=self.out, fig=self.fig, ax=ax, xlabel=xlb, ylabel=ylb, **wkw, **kwargs)
                       for w, d, ax, xlb, ylb, wkw in zip(workers, data_list, self.ax, xlabel, ylabel, worker_kw_list)]
        data_namelist = [s.get_dataname() for s in self.worker]
        # adding the index in front to make sure all button names are unique (otherwise the selection wouldn't be highlighted properly)
        if len(data_namelist) > len(set(data_namelist)):
            data_namelist = [str(i+1)+'.'+s for i, s in enumerate(data_namelist)]
        self.tabd = [s.tab for s in self.worker]
        bw, bwpadded = 50, 56  # these magic numbers seems to work well on forcing the desired button layout
        self.tb = widgets.ToggleButtons(options=data_namelist, value=data_namelist[0], description='',
                                        style={"button_width": '%dpx' % bw})
        ctrl_pnl = widgets.Box([self.tb],layout=Layout(display='flex', flex='0 0 auto', align_items='center',
                                                       width='%dpx' % (bwpadded * self.ncols)))
        self.ctrl = widgets.HBox([ctrl_pnl, self.tabd[self.tb.index]], layout=Layout(display='flex', flex='1 1 auto', width='100%'))
        self.suptitle_wgt = widgets.Text(value=None, placeholder='Plots', continuous_update=False, description='Suptitle:')
        self.time_in_suptitle = widgets.Checkbox(value=False, description='Time in suptitle')
        self.tb.observe(self.show_corresponding_tab, 'index')
        self.suptitle_wgt.observe(self.update_suptitle, 'value')
        self.time_in_suptitle.observe(self.update_suptitle, 'value')
        self.suptitle = widgets.HBox([self.suptitle_wgt, self.time_in_suptitle])
        # disable resize widgets to avoid bugs
        if sharex or sharey:
            for s in self.worker:
                s.x_min_wgt.disabled, s.y_min_wgt.disabled, s.x_max_wgt.disabled, s.y_max_wgt.disabled, \
                s.x_step_wgt.disabled, s.y_step_wgt.disabled = (True,) * 6

    @property
    def widgets_list(self):
        return self.ctrl, self.suptitle, self.out

    @property
    def time(self):
        return self.worker[0].get_time_label()

    def update_suptitle(self, *_):
        print(self.time)
        if self.suptitle_wgt.value:
            ttl = self.suptitle_wgt.value + ((', ' + self.time) if self.time_in_suptitle.value else '')
        else:
            ttl = self.time if self.time_in_suptitle.value else None
        self.fig.suptitle(ttl)
    
    def show_corresponding_tab(self, change):
        self.ctrl.children = (self.ctrl.children[0], self.tabd[self.tb.index])


class MPDirSlicer(MultiPanelCtrl):
    def __init__(self, filefilter_list, grid, interval=1000, processing=do_nothing, figsize=None, fig=None, output_widget=None,
                 sharex=False, sharey=False, **kwargs):
        if isinstance(processing, (list, tuple)):
            if len(processing) != grid[0] * grid[1]:
                raise ValueError('Expecting %d functions in processing, got %d' % (grid[0] * grid[1], len(processing)))
            else:
                ps = [{'processing' :p} for p in processing]
        else:
            ps = ({'processing' :processing},) * len(filefilter_list)
        super(MPDirSlicer, self).__init__((DirSlicer,) * len(filefilter_list), filefilter_list, grid, worker_kw_list=ps,
                                         figsize=figsize, fig=fig, output_widget=output_widget, sharex=sharex, sharey=sharey, **kwargs)
        # we need a master slider to control all subplot sliders
        self.slider = widgets.IntSlider(min=0, max=self.worker[0].file_slider.max, description='', value=0,
                                        readout=False, continuous_update=False, style={'description_width': 'initial'})
        self.play = widgets.Play(interval=interval, value=0, min=0, max=self.slider.max, description='Press play')
        self.slider.observe(self.update_all_subplots, 'value')
        widgets.jslink((self.play, 'value'), (self.slider, 'value'))

    @property
    def widgets_list(self):
        return self.ctrl, self.play, self.slider, self.worker[0].time_label, self.suptitle, self.out
    
#     @property
#     def time_label(self):
#         return self.worker[0].time_label

    def update_all_subplots(self, change):
        for s in self.worker:
            s.file_slider.value = self.slider.value
        self.update_suptitle(change)


class Animation(Slicer):
    def __init__(self, data, interval=10, step=1, **kwargs):
        super(Animation, self).__init__(data, **kwargs)
        self.play = widgets.Play(interval=interval, value=self.x, min=0, max=len(self.data.axes[self.comp]),
                                 step=step, description="Press play", disabled=False)
        self.interval_wgt = widgets.IntText(value=interval, description='Interval:', disabled=False)
        self.step_wgt = widgets.IntText(value=step, description='Step:', disabled=False)

        # link everything together
        widgets.jslink((self.play, 'value'), (self.index_slider, 'value'))
        self.interval_wgt.observe(self.update_interval, 'value')
        self.step_wgt.observe(self.update_step, 'value')

    @property
    def widgets_list(self):
        return (self.tab, self.axis_pos, self.index_slider, self.axis_selector,
                self.play, self.interval_wgt, self.step_wgt, self.out_main)

    def switch_slice_direction(self, change):
        super(Animation, self).switch_slice_direction(change)
        self.play.max = len(self.data.axes[self.comp])

    def update_interval(self, change):
        self.play.interval = change['new']

    def update_step(self, change):
        self.play.step = change['new']
