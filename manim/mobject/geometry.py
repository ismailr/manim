import warnings
import numpy as np
import math

from ..constants import *
from ..mobject.mobject import Mobject
from ..mobject.types.vectorized_mobject import VGroup
from ..mobject.types.vectorized_mobject import VMobject
from ..mobject.types.vectorized_mobject import DashedVMobject
from ..utils.config_ops import digest_config
from ..utils.iterables import adjacent_n_tuples
from ..utils.iterables import adjacent_pairs
from ..utils.simple_functions import fdiv
from ..utils.space_ops import angle_of_vector
from ..utils.space_ops import angle_between_vectors
from ..utils.space_ops import compass_directions
from ..utils.space_ops import line_intersection
from ..utils.space_ops import get_norm
from ..utils.space_ops import normalize
from ..utils.space_ops import rotate_vector


DEFAULT_DOT_RADIUS = 0.08
DEFAULT_SMALL_DOT_RADIUS = 0.04
DEFAULT_DASH_LENGTH = 0.05
DEFAULT_ARROW_TIP_LENGTH = 0.35


class TipableVMobject(VMobject):
    """
    Meant for shared functionality between Arc and Line.
    Functionality can be classified broadly into these groups:

        * Adding, Creating, Modifying tips
            - add_tip calls create_tip, before pushing the new tip
                into the TipableVMobject's list of submobjects
            - stylistic and positional configuration

        * Checking for tips
            - Boolean checks for whether the TipableVMobject has a tip
                and a starting tip

        * Getters
            - Straightforward accessors, returning information pertaining
                to the TipableVMobject instance's tip(s), its length etc

    """

    CONFIG = {
        "tip_length": DEFAULT_ARROW_TIP_LENGTH,
        # TODO
        "normal_vector": OUT,
        "tip_style": {"fill_opacity": 1, "stroke_width": 0,},
    }

    # Adding, Creating, Modifying tips

    def add_tip(self, tip_length=None, at_start=False):
        """
        Adds a tip to the TipableVMobject instance, recognising
        that the endpoints might need to be switched if it's
        a 'starting tip' or not.
        """
        tip = self.create_tip(tip_length, at_start)
        self.reset_endpoints_based_on_tip(tip, at_start)
        self.asign_tip_attr(tip, at_start)
        self.add(tip)
        return self

    def create_tip(self, tip_length=None, at_start=False):
        """
        Stylises the tip, positions it spacially, and returns
        the newly instantiated tip to the caller.
        """
        tip = self.get_unpositioned_tip(tip_length)
        self.position_tip(tip, at_start)
        return tip

    def get_unpositioned_tip(self, tip_length=None):
        """
        Returns a tip that has been stylistically configured,
        but has not yet been given a position in space.
        """
        if tip_length is None:
            tip_length = self.get_default_tip_length()
        color = self.get_color()
        style = {"fill_color": color, "stroke_color": color}
        style.update(self.tip_style)
        tip = ArrowTip(length=tip_length, **style)
        return tip

    def position_tip(self, tip, at_start=False):
        # Last two control points, defining both
        # the end, and the tangency direction
        if at_start:
            anchor = self.get_start()
            handle = self.get_first_handle()
        else:
            handle = self.get_last_handle()
            anchor = self.get_end()
        tip.rotate(angle_of_vector(handle - anchor) - PI - tip.get_angle())
        tip.shift(anchor - tip.get_tip_point())
        return tip

    def reset_endpoints_based_on_tip(self, tip, at_start):
        if self.get_length() == 0:
            # Zero length, put_start_and_end_on wouldn't work
            return self

        if at_start:
            self.put_start_and_end_on(tip.get_base(), self.get_end())
        else:
            self.put_start_and_end_on(
                self.get_start(), tip.get_base(),
            )
        return self

    def asign_tip_attr(self, tip, at_start):
        if at_start:
            self.start_tip = tip
        else:
            self.tip = tip
        return self

    # Checking for tips

    def has_tip(self):
        return hasattr(self, "tip") and self.tip in self

    def has_start_tip(self):
        return hasattr(self, "start_tip") and self.start_tip in self

    # Getters

    def pop_tips(self):
        start, end = self.get_start_and_end()
        result = VGroup()
        if self.has_tip():
            result.add(self.tip)
            self.remove(self.tip)
        if self.has_start_tip():
            result.add(self.start_tip)
            self.remove(self.start_tip)
        self.put_start_and_end_on(start, end)
        return result

    def get_tips(self):
        """
        Returns a VGroup (collection of VMobjects) containing
        the TipableVMObject instance's tips.
        """
        result = VGroup()
        if hasattr(self, "tip"):
            result.add(self.tip)
        if hasattr(self, "start_tip"):
            result.add(self.start_tip)
        return result

    def get_tip(self):
        """Returns the TipableVMobject instance's (first) tip,
        otherwise throws an exception."""
        tips = self.get_tips()
        if len(tips) == 0:
            raise Exception("tip not found")
        else:
            return tips[0]

    def get_default_tip_length(self):
        return self.tip_length

    def get_first_handle(self):
        return self.points[1]

    def get_last_handle(self):
        return self.points[-2]

    def get_end(self):
        if self.has_tip():
            return self.tip.get_start()
        else:
            return VMobject.get_end(self)

    def get_start(self):
        if self.has_start_tip():
            return self.start_tip.get_start()
        else:
            return VMobject.get_start(self)

    def get_length(self):
        start, end = self.get_start_and_end()
        return get_norm(start - end)


class Arc(TipableVMobject):
    CONFIG = {
        "radius": 1.0,
        "num_components": 9,
        "anchors_span_full_range": True,
        "arc_center": ORIGIN,
    }

    def __init__(self, start_angle=0, angle=TAU / 4, **kwargs):
        self.start_angle = start_angle
        self.angle = angle
        self._failed_to_get_center = False
        VMobject.__init__(self, **kwargs)

    def generate_points(self):
        self.set_pre_positioned_points()
        self.scale(self.radius, about_point=ORIGIN)
        self.shift(self.arc_center)

    def set_pre_positioned_points(self):
        anchors = np.array(
            [
                np.cos(a) * RIGHT + np.sin(a) * UP
                for a in np.linspace(
                    self.start_angle,
                    self.start_angle + self.angle,
                    self.num_components,
                )
            ]
        )
        # Figure out which control points will give the
        # Appropriate tangent lines to the circle
        d_theta = self.angle / (self.num_components - 1.0)
        tangent_vectors = np.zeros(anchors.shape)
        # Rotate all 90 degress, via (x, y) -> (-y, x)
        tangent_vectors[:, 1] = anchors[:, 0]
        tangent_vectors[:, 0] = -anchors[:, 1]
        # Use tangent vectors to deduce anchors
        handles1 = anchors[:-1] + (d_theta / 3) * tangent_vectors[:-1]
        handles2 = anchors[1:] - (d_theta / 3) * tangent_vectors[1:]
        self.set_anchors_and_handles(
            anchors[:-1], handles1, handles2, anchors[1:],
        )

    def get_arc_center(self, warning=True):
        """
        Looks at the normals to the first two
        anchors, and finds their intersection points
        """
        # First two anchors and handles
        a1, h1, h2, a2 = self.points[:4]
        # Tangent vectors
        t1 = h1 - a1
        t2 = h2 - a2
        # Normals
        n1 = rotate_vector(t1, TAU / 4)
        n2 = rotate_vector(t2, TAU / 4)
        try:
            return line_intersection(line1=(a1, a1 + n1), line2=(a2, a2 + n2),)
        except Exception:
            if warning:
                warnings.warn("Can't find Arc center, using ORIGIN instead")
            self._failed_to_get_center = True
            return np.array(ORIGIN)

    def move_arc_center_to(self, point):
        self.shift(point - self.get_arc_center())
        return self

    def stop_angle(self):
        return angle_of_vector(self.points[-1] - self.get_arc_center()) % TAU


class ArcBetweenPoints(Arc):
    """
    Inherits from Arc and additionally takes 2 points between which the arc is spanned.
    """

    def __init__(self, start, end, angle=TAU / 4, radius=None, **kwargs):
        if radius is not None:
            self.radius = radius
            if radius < 0:
                sign = -2
                radius *= -1
            else:
                sign = 2
            halfdist = np.linalg.norm(np.array(start) - np.array(end)) / 2
            if radius < halfdist:
                raise ValueError(
                    "ArcBetweenPoints called with a radius that is "
                    "smaller than half the distance between the points."
                )
            arc_height = radius - math.sqrt(radius ** 2 - halfdist ** 2)
            angle = math.acos((radius - arc_height) / radius) * sign

        Arc.__init__(
            self, angle=angle, **kwargs,
        )
        if angle == 0:
            self.set_points_as_corners([LEFT, RIGHT])
        self.put_start_and_end_on(start, end)

        if radius is None:
            center = self.get_arc_center(warning=False)
            if not self._failed_to_get_center:
                self.radius = np.linalg.norm(np.array(start) - np.array(center))
            else:
                self.radius = math.inf


class CurvedArrow(ArcBetweenPoints):
    def __init__(self, start_point, end_point, **kwargs):
        ArcBetweenPoints.__init__(self, start_point, end_point, **kwargs)
        self.add_tip()


class CurvedDoubleArrow(CurvedArrow):
    def __init__(self, start_point, end_point, **kwargs):
        CurvedArrow.__init__(self, start_point, end_point, **kwargs)
        self.add_tip(at_start=True)


class Circle(Arc):
    CONFIG = {"color": RED, "close_new_points": True, "anchors_span_full_range": False}

    def __init__(self, **kwargs):
        Arc.__init__(self, 0, TAU, **kwargs)

    def surround(self, mobject, dim_to_match=0, stretch=False, buffer_factor=1.2):
        # Ignores dim_to_match and stretch; result will always be a circle
        # TODO: Perhaps create an ellipse class to handle singele-dimension stretching

        # Something goes wrong here when surrounding lines?
        # TODO: Figure out and fix
        self.replace(mobject, dim_to_match, stretch)

        self.set_width(np.sqrt(mobject.get_width() ** 2 + mobject.get_height() ** 2))
        self.scale(buffer_factor)

    def point_at_angle(self, angle):
        start_angle = angle_of_vector(self.points[0] - self.get_center())
        return self.point_from_proportion((angle - start_angle) / TAU)


class Dot(Circle):
    CONFIG = {
        "radius": DEFAULT_DOT_RADIUS,
        "stroke_width": 0,
        "fill_opacity": 1.0,
        "color": WHITE,
    }

    def __init__(self, point=ORIGIN, **kwargs):
        Circle.__init__(self, arc_center=point, **kwargs)


class SmallDot(Dot):
    CONFIG = {
        "radius": DEFAULT_SMALL_DOT_RADIUS,
    }


class Ellipse(Circle):
    CONFIG = {"width": 2, "height": 1}

    def __init__(self, **kwargs):
        Circle.__init__(self, **kwargs)
        self.set_width(self.width, stretch=True)
        self.set_height(self.height, stretch=True)


class AnnularSector(Arc):
    CONFIG = {
        "inner_radius": 1,
        "outer_radius": 2,
        "angle": TAU / 4,
        "start_angle": 0,
        "fill_opacity": 1,
        "stroke_width": 0,
        "color": WHITE,
    }

    def generate_points(self):
        inner_arc, outer_arc = [
            Arc(
                start_angle=self.start_angle,
                angle=self.angle,
                radius=radius,
                arc_center=self.arc_center,
            )
            for radius in (self.inner_radius, self.outer_radius)
        ]
        outer_arc.reverse_points()
        self.append_points(inner_arc.points)
        self.add_line_to(outer_arc.points[0])
        self.append_points(outer_arc.points)
        self.add_line_to(inner_arc.points[0])


class Sector(AnnularSector):
    CONFIG = {"outer_radius": 1, "inner_radius": 0}


class Annulus(Circle):
    CONFIG = {
        "inner_radius": 1,
        "outer_radius": 2,
        "fill_opacity": 1,
        "stroke_width": 0,
        "color": WHITE,
        "mark_paths_closed": False,
    }

    def generate_points(self):
        self.radius = self.outer_radius
        outer_circle = Circle(radius=self.outer_radius)
        inner_circle = Circle(radius=self.inner_radius)
        inner_circle.reverse_points()
        self.append_points(outer_circle.points)
        self.append_points(inner_circle.points)
        self.shift(self.arc_center)


class Line(TipableVMobject):
    CONFIG = {
        "buff": 0,
        "path_arc": None,  # angle of arc specified here
    }

    def __init__(self, start=LEFT, end=RIGHT, **kwargs):
        digest_config(self, kwargs)
        self.set_start_and_end_attrs(start, end)
        VMobject.__init__(self, **kwargs)

    def generate_points(self):
        if self.path_arc:
            arc = ArcBetweenPoints(self.start, self.end, angle=self.path_arc)
            self.set_points(arc.points)
        else:
            self.set_points_as_corners([self.start, self.end])
        self.account_for_buff()

    def set_path_arc(self, new_value):
        self.path_arc = new_value
        self.generate_points()

    def account_for_buff(self):
        if self.buff == 0:
            return
        #
        if self.path_arc == 0:
            length = self.get_length()
        else:
            length = self.get_arc_length()
        #
        if length < 2 * self.buff:
            return
        buff_proportion = self.buff / length
        self.pointwise_become_partial(self, buff_proportion, 1 - buff_proportion)
        return self

    def set_start_and_end_attrs(self, start, end):
        # If either start or end are Mobjects, this
        # gives their centers
        rough_start = self.pointify(start)
        rough_end = self.pointify(end)
        vect = normalize(rough_end - rough_start)
        # Now that we know the direction between them,
        # we can the appropriate boundary point from
        # start and end, if they're mobjects
        self.start = self.pointify(start, vect)
        self.end = self.pointify(end, -vect)

    def pointify(self, mob_or_point, direction=None):
        if isinstance(mob_or_point, Mobject):
            mob = mob_or_point
            if direction is None:
                return mob.get_center()
            else:
                return mob.get_boundary_point(direction)
        return np.array(mob_or_point)

    def put_start_and_end_on(self, start, end):
        curr_start, curr_end = self.get_start_and_end()
        if np.all(curr_start == curr_end):
            # TODO, any problems with resetting
            # these attrs?
            self.start = start
            self.end = end
            self.generate_points()
        return super().put_start_and_end_on(start, end)

    def get_vector(self):
        return self.get_end() - self.get_start()

    def get_unit_vector(self):
        return normalize(self.get_vector())

    def get_angle(self):
        return angle_of_vector(self.get_vector())

    def get_slope(self):
        return np.tan(self.get_angle())

    def set_angle(self, angle):
        self.rotate(
            angle - self.get_angle(), about_point=self.get_start(),
        )

    def set_length(self, length):
        self.scale(length / self.get_length())

    def set_opacity(self, opacity, family=True):
        # Overwrite default, which would set
        # the fill opacity
        self.set_stroke(opacity=opacity)
        if family:
            for sm in self.submobjects:
                sm.set_opacity(opacity, family)
        return self


class DashedLine(Line):
    CONFIG = {
        "dash_length": DEFAULT_DASH_LENGTH,
        "dash_spacing": None,
        "positive_space_ratio": 0.5,
    }

    def __init__(self, *args, **kwargs):
        Line.__init__(self, *args, **kwargs)
        ps_ratio = self.positive_space_ratio
        num_dashes = self.calculate_num_dashes(ps_ratio)
        dashes = DashedVMobject(
            self, num_dashes=num_dashes, positive_space_ratio=ps_ratio
        )
        self.clear_points()
        self.add(*dashes)

    def calculate_num_dashes(self, positive_space_ratio):
        try:
            full_length = self.dash_length / positive_space_ratio
            return int(np.ceil(self.get_length() / full_length))
        except ZeroDivisionError:
            return 1

    def calculate_positive_space_ratio(self):
        return fdiv(self.dash_length, self.dash_length + self.dash_spacing,)

    def get_start(self):
        if len(self.submobjects) > 0:
            return self.submobjects[0].get_start()
        else:
            return Line.get_start(self)

    def get_end(self):
        if len(self.submobjects) > 0:
            return self.submobjects[-1].get_end()
        else:
            return Line.get_end(self)

    def get_first_handle(self):
        return self.submobjects[0].points[1]

    def get_last_handle(self):
        return self.submobjects[-1].points[-2]


class TangentLine(Line):
    CONFIG = {"length": 1, "d_alpha": 1e-6}

    def __init__(self, vmob, alpha, **kwargs):
        digest_config(self, kwargs)
        da = self.d_alpha
        a1 = np.clip(alpha - da, 0, 1)
        a2 = np.clip(alpha + da, 0, 1)
        super().__init__(
            vmob.point_from_proportion(a1), vmob.point_from_proportion(a2), **kwargs
        )
        self.scale(self.length / self.get_length())


class Elbow(VMobject):
    CONFIG = {
        "width": 0.2,
        "angle": 0,
    }

    def __init__(self, **kwargs):
        VMobject.__init__(self, **kwargs)
        self.set_points_as_corners([UP, UP + RIGHT, RIGHT])
        self.set_width(self.width, about_point=ORIGIN)
        self.rotate(self.angle, about_point=ORIGIN)


class Arrow(Line):
    CONFIG = {
        "stroke_width": 6,
        "buff": MED_SMALL_BUFF,
        "max_tip_length_to_length_ratio": 0.25,
        "max_stroke_width_to_length_ratio": 5,
        "preserve_tip_size_when_scaling": True,
    }

    def __init__(self, *args, **kwargs):
        Line.__init__(self, *args, **kwargs)
        # TODO, should this be affected when
        # Arrow.set_stroke is called?
        self.initial_stroke_width = self.stroke_width
        self.add_tip()
        self.set_stroke_width_from_length()

    def scale(self, factor, **kwargs):
        if self.get_length() == 0:
            return self

        has_tip = self.has_tip()
        has_start_tip = self.has_start_tip()
        if has_tip or has_start_tip:
            old_tips = self.pop_tips()

        VMobject.scale(self, factor, **kwargs)
        self.set_stroke_width_from_length()

        # So horribly confusing, must redo
        if has_tip:
            self.add_tip()
            old_tips[0].points[:, :] = self.tip.points
            self.remove(self.tip)
            self.tip = old_tips[0]
            self.add(self.tip)
        if has_start_tip:
            self.add_tip(at_start=True)
            old_tips[1].points[:, :] = self.start_tip.points
            self.remove(self.start_tip)
            self.start_tip = old_tips[1]
            self.add(self.start_tip)
        return self

    def get_normal_vector(self):
        p0, p1, p2 = self.tip.get_start_anchors()[:3]
        return normalize(np.cross(p2 - p1, p1 - p0))

    def reset_normal_vector(self):
        self.normal_vector = self.get_normal_vector()
        return self

    def get_default_tip_length(self):
        max_ratio = self.max_tip_length_to_length_ratio
        return min(self.tip_length, max_ratio * self.get_length(),)

    def set_stroke_width_from_length(self):
        max_ratio = self.max_stroke_width_to_length_ratio
        self.set_stroke(
            width=min(self.initial_stroke_width, max_ratio * self.get_length(),),
            family=False,
        )
        return self

    # TODO, should this be the default for everything?
    def copy(self):
        return self.deepcopy()


class Vector(Arrow):
    CONFIG = {
        "buff": 0,
    }

    def __init__(self, direction=RIGHT, **kwargs):
        if len(direction) == 2:
            direction = np.append(np.array(direction), 0)
        Arrow.__init__(self, ORIGIN, direction, **kwargs)


class DoubleArrow(Arrow):
    def __init__(self, *args, **kwargs):
        Arrow.__init__(self, *args, **kwargs)
        self.add_tip(at_start=True)


class CubicBezier(VMobject):
    def __init__(self, points, **kwargs):
        VMobject.__init__(self, **kwargs)
        self.set_points(points)


class Polygon(VMobject):
    CONFIG = {
        "color": BLUE,
    }

    def __init__(self, *vertices, **kwargs):
        VMobject.__init__(self, **kwargs)
        self.set_points_as_corners([*vertices, vertices[0]])

    def get_vertices(self):
        return self.get_start_anchors()

    def round_corners(self, radius=0.5):
        vertices = self.get_vertices()
        arcs = []
        for v1, v2, v3 in adjacent_n_tuples(vertices, 3):
            vect1 = v2 - v1
            vect2 = v3 - v2
            unit_vect1 = normalize(vect1)
            unit_vect2 = normalize(vect2)
            angle = angle_between_vectors(vect1, vect2)
            # Negative radius gives concave curves
            angle *= np.sign(radius)
            # Distance between vertex and start of the arc
            cut_off_length = radius * np.tan(angle / 2)
            # Determines counterclockwise vs. clockwise
            sign = np.sign(np.cross(vect1, vect2)[2])
            arc = ArcBetweenPoints(
                v2 - unit_vect1 * cut_off_length,
                v2 + unit_vect2 * cut_off_length,
                angle=sign * angle,
            )
            arcs.append(arc)

        self.clear_points()
        # To ensure that we loop through starting with last
        arcs = [arcs[-1], *arcs[:-1]]
        for arc1, arc2 in adjacent_pairs(arcs):
            self.append_points(arc1.points)
            line = Line(arc1.get_end(), arc2.get_start())
            # Make sure anchors are evenly distributed
            len_ratio = line.get_length() / arc1.get_arc_length()
            line.insert_n_curves(int(arc1.get_num_curves() * len_ratio))
            self.append_points(line.get_points())
        return self


class RegularPolygon(Polygon):
    CONFIG = {
        "start_angle": None,
    }

    def __init__(self, n=6, **kwargs):
        digest_config(self, kwargs, locals())
        if self.start_angle is None:
            if n % 2 == 0:
                self.start_angle = 0
            else:
                self.start_angle = 90 * DEGREES
        start_vect = rotate_vector(RIGHT, self.start_angle)
        vertices = compass_directions(n, start_vect)
        Polygon.__init__(self, *vertices, **kwargs)


class ArcPolygon(VMobject):
    """
    A more versatile polygon, made from arcs.

    Parameters
    ----------
    *arcs : Arc or ArcBetweenPoints
    
    Example
    -------
    ArcPolygon(arc0,arc1,arc2,arcN,**kwargs)

    
    For proper appearance the arcs should seamlessly connect:
    [a,b][b,c][c,a]
    If they don't, the gaps will be filled in with straight lines.

    ArcPolygon doubles as a VGroup for the input arcs, so it stores
    the passed arcs like a VGroup would, but also additionally uses the
    arcs to generate new points for itself.
    This is so that the ArcPolygon can be directly manipulated while
    assuring that the stored arcs, accessible via ArcPolygon.arcs, still
    return correct values.

    Because arcs are stored like this, if only the generated ArcPolygon
    itself is supposed to be visible, the passed arcs have to be made
    invisible (for example with "stroke_width": 0).
    """

    def __init__(self, *arcs, **kwargs):
        if not all(
            [isinstance(m, Arc) or isinstance(m, ArcBetweenPoints) for m in arcs]
        ):
            raise ValueError(
                "All ArcPolygon submobjects must be of type Arc/ArcBetweenPoints"
            )
        VMobject.__init__(self, **kwargs)
        # Adding the arcs like this makes ArcPolygon double as a VGroup.
        # Also makes changes to the ArcPolygon, such as scaling, affect
        # the arcs, so that their new values are usable.
        self.add(*arcs)
        # This enables the use of ArcPolygon.arcs as a convenience
        # because ArcPolygon[0] returns itself, not the first Arc.
        self.arcs = [*arcs]
        for arc1, arc2 in adjacent_pairs(arcs):
            self.append_points(arc1.points)
            line = Line(arc1.get_end(), arc2.get_start())
            len_ratio = line.get_length() / arc1.get_arc_length()
            if math.isnan(len_ratio) or math.isinf(len_ratio):
                continue
            line.insert_n_curves(int(arc1.get_num_curves() * len_ratio))
            self.append_points(line.get_points())


class Triangle(RegularPolygon):
    def __init__(self, **kwargs):
        RegularPolygon.__init__(self, n=3, **kwargs)


class ArrowTip(Triangle):
    CONFIG = {
        "fill_opacity": 1,
        "stroke_width": 0,
        "length": DEFAULT_ARROW_TIP_LENGTH,
        "start_angle": PI,
    }

    def __init__(self, **kwargs):
        Triangle.__init__(self, **kwargs)
        self.set_width(self.length)
        self.set_height(self.length, stretch=True)

    def get_base(self):
        return self.point_from_proportion(0.5)

    def get_tip_point(self):
        return self.points[0]

    def get_vector(self):
        return self.get_tip_point() - self.get_base()

    def get_angle(self):
        return angle_of_vector(self.get_vector())

    def get_length(self):
        return get_norm(self.get_vector())


class Rectangle(Polygon):
    CONFIG = {
        "color": WHITE,
        "height": 2.0,
        "width": 4.0,
        "mark_paths_closed": True,
        "close_new_points": True,
    }

    def __init__(self, **kwargs):
        Polygon.__init__(self, UL, UR, DR, DL, **kwargs)
        self.set_width(self.width, stretch=True)
        self.set_height(self.height, stretch=True)


class Square(Rectangle):
    CONFIG = {
        "side_length": 2.0,
    }

    def __init__(self, **kwargs):
        digest_config(self, kwargs)
        Rectangle.__init__(
            self, height=self.side_length, width=self.side_length, **kwargs
        )


class RoundedRectangle(Rectangle):
    CONFIG = {
        "corner_radius": 0.5,
    }

    def __init__(self, **kwargs):
        Rectangle.__init__(self, **kwargs)
        self.round_corners(self.corner_radius)


class Tiling(VMobject):
    """
    The purpose of this class is to create tilings/tesselations.
    Tilings can also be seemlessly transformed into each other.
    This requires their ranges to be the same, tiles to be oriented and
    rotated the correct way, as well as having a vertex setup that
    allows proper transformations.
    
    Parameters
    ----------
    tile_prototype : Mobject or function(x,y) that returns a Mobject
    x_offset : nested list of Mobject methods and values
    y_offset : nested list of Mobject methods and values
    x_range : range
    y_range : range
    
    
    The tile prototype can be any Mobject (also groups) or a function.
    The function format is function(x,y), taking in the tile location
    as x and y (int) and returns a Mobject to be used as a tile there.
    Using groups or functions allows the tiling to contain multiple
    different tiles or to simplify the following offset functions.
    
    Next are two nested lists that determine how
    the tiles are arranged, x_offset and y_offset.
    More on this in the Examples section.

    Last are two ranges, x_range and y_range: If both ranges are
    range(-1,1,1), that would result in a square grid of 9 tiles.

    A Tiling can be directly drawn like a VGroup.
    Tiling.tile_dictionary[x][y] can be used to access individual tiles,
    to color them for example.
    
    Examples
    --------
    x_offset and y_offset examples:
    Example for a shift along the X-Axis, 1 in the positive direction:
    x_offset=[[Mobject.shift,[1,0,0]]]

    The origin tile at [x0,y0] won't be moved, but the tile at [x1,y0]
    will be moved to [1,0,0]. Likewise the tile at [x4,y0] will be moved
    to [4,0,0]
    
    Every step within the tiling applies a full sublist.
    Example for a shift with simultaneous rotation:
    [[Mobject.shift,[1,0,0],Mobject.rotate,np.pi]]

    This would move the tile at [x1,y0] to [1,0,0] and rotate it 180°.
    
    When multiple sublists are passed, they are applied alternately.
    Example for alternating shifting and rotating:
    [[Mobject.shift,[1,0,0]],[Mobject.rotate,np.pi]]

    This would move the tile at [x1,y0] to [1,0,0], but wouldn't rotate
    it yet. The tile at [x2,y0] would still be moved to [1,0,0] and also
    rotated by 180°. The tile at [x3,y0] would be moved to [2,0,0] and
    still rotated by 180°.

    Full example:
    Tiling(Square(),
           [[Mobject.shift,[2.1,0,0]]],
           [[Mobject.shift,[0,2.1,0]]],
           range(-1,1),
           range(-1,1))
    """

    def __init__(self, tile_prototype, x_offset, y_offset, x_range, y_range, **kwargs):
        VMobject.__init__(self, **kwargs)
        # Add one more to the ranges, so that a range(-1,1,1)
        # also gives us 3 tiles, [-1,0,1] as opposed to 2 [-1,0]
        self.x_range = range(x_range.start, x_range.stop + x_range.step, x_range.step)
        self.y_range = range(y_range.start, y_range.stop + y_range.step, y_range.step)
        self.x_offset = x_offset
        self.y_offset = y_offset

        # We need the tiles array for a VGroup, which in turn we need
        # to draw the tiling and adjust it.
        # Trying to draw the tiling directly will not properly work.
        self.tile_prototype = tile_prototype
        self.tile_dictionary = {}
        self.tile_init_loop()

    def tile_init_loop(self):
        """
        Loops through the ranges, creates the tiles by copying the
        prototype, adds them to self and sorts them into the dictionary.
        Calls apply_transforms to apply passed methods.
        """
        for x in self.x_range:
            self.tile_dictionary[x] = {}
            for y in self.y_range:
                if callable(self.tile_prototype):
                    tile = self.tile_prototype(x, y).deepcopy()
                else:
                    tile = self.tile_prototype.deepcopy()
                self.apply_transforms(x, y, tile)
                self.add(tile)
                self.tile_dictionary[x][y] = tile
        # TODO: Once the config overhaul is far enough:
        # Implement a way to apply kwargs to all tiles.
        # The reason for this is that if multiple tilings
        # are instantiated from one prototype, having a different basic
        # tile setup is rather complicated now (set_fill etc).

    def apply_transforms(self, x, y, tile):
        """
        Calls transform_tile once per dimension to position tiles.
        Written like this to allow easy extending by Honeycomb.
        """
        self.transform_tile(x, self.x_offset, tile)
        self.transform_tile(y, self.y_offset, tile)

    def transform_tile(self, position, offset, tile):
        """
        This method computes and applies the offsets for the tiles,
        in the given dimension.
        multiplies inputs, which requires arrays to be numpy arrays.
        """
        # The number of different offsets the current axis has
        offsets_nr = len(offset)
        for i in range(offsets_nr):
            for j in range(int(len(offset[i]) / 2)):
                if position < 0:
                    # Magnitude is calculated as the length of a range.
                    # The range starts at 0, adjusting for the number
                    # of different offset functions, stops at the target
                    # position, and uses the amount of different
                    # offset functions as the step.
                    magnitude = len(range(-i, position, -offsets_nr)) * -1
                    offset[-1 - i][0 + j * 2](
                        tile, magnitude * np.array(offset[-1 - i][1 + j * 2])
                    )
                else:
                    magnitude = len(range(i, position, offsets_nr))
                    offset[i][0 + j * 2](
                        tile, magnitude * np.array(offset[i][1 + j * 2])
                    )
                    
class TilingMK2(VMobject):
    def __init__(self, tile_function, x_range, y_range, tile_prototype=None **kwargs):
        VMobject.__init__(self, **kwargs)
        # Add one more to the ranges, so that a range(-1,1,1)
        # also gives us 3 tiles, [-1,0,1] as opposed to 2 [-1,0]
        self.x_range = range(x_range.start, x_range.stop + x_range.step, x_range.step)
        self.y_range = range(y_range.start, y_range.stop + y_range.step, y_range.step)
        self.x_offset = x_offset
        self.y_offset = y_offset

        # We need the tiles array for a VGroup, which in turn we need
        # to draw the tiling and adjust it.
        # Trying to draw the tiling directly will not properly work.
        self.tile_prototype = tile_prototype
        self.tile_dictionary = {}
        self.tile_init_loop()

    def tile_init_loop(self):
        """
        Loops through the ranges, creates the tiles by copying the
        prototype, adds them to self and sorts them into the dictionary.
        Calls apply_transforms to apply passed methods.
        """
        for x in self.x_range:
            self.tile_dictionary[x] = {}
            for y in self.y_range:
                if tile_prototype==None:
                    tile = self.tile_prototype(x, y).deepcopy()
                else:
                    tile = self.tile_prototype.deepcopy()
                self.apply_transforms(x, y, tile)
                self.add(tile)
                self.tile_dictionary[x][y] = tile
        # TODO: Once the config overhaul is far enough:
        # Implement a way to apply kwargs to all tiles.
        # The reason for this is that if multiple tilings
        # are instantiated from one prototype, having a different basic
        # tile setup is rather complicated now (set_fill etc).

    def apply_transforms(self, x, y, tile):
        """
        Calls transform_tile once per dimension to position tiles.
        Written like this to allow easy extending by Honeycomb.
        """
        self.transform_tile(x, self.x_offset, tile)
        self.transform_tile(y, self.y_offset, tile)

    def transform_tile(self, position, offset, tile):
        """
        This method computes and applies the offsets for the tiles,
        in the given dimension.
        multiplies inputs, which requires arrays to be numpy arrays.
        """
        # The number of different offsets the current axis has
        offsets_nr = len(offset)
        for i in range(offsets_nr):
            for j in range(int(len(offset[i]) / 2)):
                if position < 0:
                    # Magnitude is calculated as the length of a range.
                    # The range starts at 0, adjusting for the number
                    # of different offset functions, stops at the target
                    # position, and uses the amount of different
                    # offset functions as the step.
                    magnitude = len(range(-i, position, -offsets_nr)) * -1
                    offset[-1 - i][0 + j * 2](
                        tile, magnitude * np.array(offset[-1 - i][1 + j * 2])
                    )
                else:
                    magnitude = len(range(i, position, offsets_nr))
                    offset[i][0 + j * 2](
                        tile, magnitude * np.array(offset[i][1 + j * 2])
                    )

class EdgeVertexGraph:
    """
    This class is for visual representation of graphs for graph theory.

    It's instantiated with a dictionary that represents the graph, and
    optionally which types of Mobject to use as vertices/edges and
    dicts for their standard attributes.
    
    Parameters
    ----------
    graph : dict
    vertex_type : MobjectClass, optional (default: Circle)
    vertex_config : dict, optional
    edge_type : MobjectClass, optional (default: ArcBetweenPoints)
    edge_config : dict, optional

    
    The keys for the graph have to be of type int in ascending order,
    with each number denoting a vertex.
    The values are lists with 3 elements. A list of coordinates,
    a list of connected vertices in int, pointing to the vertices
    defined as the graph keys, and a configuration dictionary.
    The coordinates determine the position of the vertex.
    The list of connected vertices determines between which vertices
    edges are. For clarity it's possible to have an edge defined in both
    directions, but it'll be drawn once, from lower to higher number.
    For example if vertex 2 is connected to vertex 0, that's ignored.
    The config dictionary is used while initializing the vertex and
    will override values passed via vertex_config.

    Examples
    --------
    Full example:
    g = {0: [[0,0,0], [1, 2], {"color": BLUE}],
         1: [[1,0,0], [0, 2], {"color": GRAY}],
         2: [[0,1,0], [0, 1], {"color": PINK}]}
    EdgeVertexGraph(g,vertex_config={"radius": 0.2,"fill_opacity": 1},
                    edge_config={"stroke_width": 5,"color": RED})

    Individual config dictionaries can also be passed to edges.
    Example:
    g = {0: [[0,0,0], [[1,{"angle": 2}], [2,{"color": WHITE}]]...

    
    Use EdgeVertexGraph.vertices/EdgeVertexGraph.edges for drawing.
    """

    def __init__(
        self,
        graph,
        vertex_type=Circle,
        vertex_config={},
        edge_type=ArcBetweenPoints,
        edge_config={},
        **kwargs
    ):
        if not all(isinstance(n, int) for n in graph.keys()):
            raise ValueError("All keys for the graph dictionary have to be of type int")
        if not all(
            all(isinstance(m, int) or isinstance(m, list) for m in n[1])
            for n in graph.values()
        ):
            raise ValueError(
                "Invalid Edge definition for EdgeVertexGraph. Use int or [int,dict]."
            )

        self.vertices = VGroup()
        self.edges = VGroup()

        # Loops over all key/value pairs of the graph dict.
        for vertex, attributes in graph.items():
            self.vertices.add(
                vertex_type(**{**vertex_config, **attributes[2]}).shift(attributes[0])
            )
            for edge_definition in attributes[1]:
                if isinstance(edge_definition, int):
                    vertex_number = edge_definition
                    edge_kwargs = {}
                elif isinstance(edge_definition, list):
                    vertex_number = edge_definition[0]
                    edge_kwargs = edge_definition[1]
                if vertex < vertex_number:
                    edge = edge_type(
                        attributes[0],
                        graph[vertex_number][0],
                        **{"angle": 0, **edge_config, **edge_kwargs},
                    )
                    self.edges.add(edge)
