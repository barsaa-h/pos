import os
import sys
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from posgtk.scaling import init_scaling, get_scale, scaled_px, reset


def test_scaling_environment_override():
    reset()
    os.environ["POS_GTK_SCALE"] = "1.5"
    try:
        scale = init_scaling()
        assert scale == 1.5
        assert get_scale() == 1.5
        assert scaled_px(100) == 150
    finally:
        del os.environ["POS_GTK_SCALE"]


def test_scaling_no_display():
    reset()
    # When display is None or not available, it should fallback gracefully
    scale = init_scaling(display=None)
    assert scale >= 0.5 and scale <= 3.0


def test_scaling_mock_geometry_hd():
    reset()
    mock_display = MagicMock()
    mock_monitor = MagicMock()
    
    mock_geo = MagicMock()
    mock_geo.width = 1920
    mock_geo.height = 1080
    
    mock_monitor.get_geometry.return_value = mock_geo
    mock_display.get_primary_monitor.return_value = mock_monitor
    
    scale = init_scaling(mock_display)
    # scale_h = 1080 / 768 = 1.406
    # scale_w = 1920 / 1366 = 1.405
    # min = 1.405 -> rounded to 1 decimal place = 1.4
    assert scale == 1.4
    assert get_scale() == 1.4
    assert scaled_px(100) == 140


def test_scaling_mock_geometry_small():
    reset()
    mock_display = MagicMock()
    mock_monitor = MagicMock()
    
    mock_geo = MagicMock()
    mock_geo.width = 1024
    mock_geo.height = 768
    
    mock_monitor.get_geometry.return_value = mock_geo
    mock_display.get_primary_monitor.return_value = mock_monitor
    
    scale = init_scaling(mock_display)
    # scale_h = 768 / 768 = 1.0
    # scale_w = 1024 / 1366 = 0.749
    # min = 0.749 -> rounded to 1 decimal place = 0.7
    assert scale == 0.7
    assert get_scale() == 0.7
    assert scaled_px(100) == 70
