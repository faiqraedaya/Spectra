from ultralytics import YOLO

# Load your trained model
model = YOLO('best.pt')

# Run prediction on an image
results = model(r"C:\Users\FJR\OneDrive\2_Programs\2521P Odin\image.jpg")

# Show results
for result in results:
    result.show()  # Opens a window with detections
