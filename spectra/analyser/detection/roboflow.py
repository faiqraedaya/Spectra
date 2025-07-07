from typing import List

from roboflow import Roboflow

from PySide6.QtCore import QThread, Signal
from detection.types import Detection

class RoboflowAnalysisThread(QThread):
    """Thread for running Roboflow analysis without blocking UI
    
    This thread should ONLY emit signals to communicate with the main thread.
    It should NEVER directly access or modify UI components.
    All UI updates must be handled by the main thread through signal-slot connections.
    """
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
        """Run the analysis in background thread
        
        This method runs in a separate thread and should only:
        1. Perform the analysis work
        2. Emit signals to communicate progress and results
        3. NOT access any UI components directly
        """
        try:
            rf = Roboflow(api_key=self.api_key)
            project = rf.workspace().project("schemas")
            model = project.version(1).model
            
            all_detections = []
            
            for i, image_path in enumerate(self.image_paths):
                # Emit progress signal (will be handled on main thread)
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
            
            # Emit completion signal (will be handled on main thread)
            self.analysis_complete.emit(all_detections)
        except Exception as e:
            # Emit error signal (will be handled on main thread)
            self.error_occurred.emit(str(e))