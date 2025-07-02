from typing import List

from roboflow import Roboflow

from PySide6.QtCore import QThread, Signal
from detection.types import Detection

class RoboflowAnalysisThread(QThread):
    """Thread for running Roboflow analysis without blocking UI"""
    analysis_complete = Signal(list)
    error_occurred = Signal(str)
    progress_updated = Signal(int, int)  # current, total
    
    def __init__(self, api_key: str, image_paths: List[str], 
                 conf_threshold: float, overlap_threshold: int):
        super().__init__()
        self.api_key = api_key
        self.image_paths = image_paths
        self.conf_threshold = conf_threshold
        self.overlap_threshold = overlap_threshold
    
    def run(self):
        try:
            rf = Roboflow(api_key=self.api_key)
            project = rf.workspace().project("schemas")
            model = project.version(1).model
            
            all_detections = []
            
            for i, image_path in enumerate(self.image_paths):
                self.progress_updated.emit(i + 1, len(self.image_paths))
                
                result = model.predict(
                    image_path, 
                    confidence=int(self.conf_threshold * 100),
                    overlap=self.overlap_threshold
                ).json()
                
                page_detections = []
                for prediction in result["predictions"]:
                    x_center = prediction["x"]
                    y_center = prediction["y"]
                    width = prediction["width"]
                    height = prediction["height"]
                    
                    x1 = int(x_center - width / 2)
                    y1 = int(y_center - height / 2)
                    x2 = int(x_center + width / 2)
                    y2 = int(y_center + height / 2)
                    
                    detection = Detection(
                        name=prediction["class"],
                        confidence=prediction["confidence"],
                        bbox=(x1, y1, x2, y2),
                        page_num=i + 1,
                        source="model"
                    )
                    page_detections.append(detection)
                
                all_detections.extend(page_detections)
            
            self.analysis_complete.emit(all_detections)
        except Exception as e:
            self.error_occurred.emit(str(e))