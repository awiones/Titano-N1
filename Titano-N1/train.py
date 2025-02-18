import os
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import ResNet50V2, MobileNetV2
from tensorflow.keras.layers import Input, Dense, GlobalAveragePooling2D, Dropout, BatchNormalization, Conv2D, MaxPooling2D, Flatten
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
import matplotlib.pyplot as plt
import json

# Configure GPU memory growth to avoid CUDA errors
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(f"GPU configuration error: {e}")

def check_and_download_images():
    dataset_dir = 'dataset'
    train_dir = os.path.join(dataset_dir, 'train')
    val_dir = os.path.join(dataset_dir, 'val')

    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n=== Image Dataset Management ===")
        
        train_images = sum([len(files) for r, d, files in os.walk(train_dir)])
        val_images = sum([len(files) for r, d, files in os.walk(val_dir)])
        
        print(f"\nCurrent dataset status:")
        print(f"Training images: {train_images}")
        print(f"Validation images: {val_images}")
        
        if train_images == 0 and val_images == 0:
            print("\nNo images found in dataset folders.")
        
        print("\nOptions:")
        print("1. Download more images")
        print("2. Continue to training")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            import download
            download.main()
        elif choice == '2':
            if train_images == 0 or val_images == 0:
                input("Error: Cannot train without images. Press Enter to continue...")
                continue
            return True
        elif choice == '3':
            print("Exiting...")
            exit()
        else:
            input("Invalid choice. Press Enter to continue...")

def get_num_classes(train_dir, val_dir):
    train_classes = set(os.listdir(train_dir))
    val_classes = set(os.listdir(val_dir))
    
    if not train_classes:
        raise ValueError("No classes found in training directory")
    
    if train_classes != val_classes:
        print("Warning: Mismatch between training and validation classes!")
        print(f"Training classes: {train_classes}")
        print(f"Validation classes: {val_classes}")
        print("\nOnly matching classes will be used.")
        
    common_classes = sorted(train_classes.intersection(val_classes))
    if not common_classes:
        raise ValueError("No matching classes between training and validation sets")
        
    return len(common_classes), common_classes

def create_light_model(input_shape, num_classes):
    inputs = Input(shape=input_shape)
    x = Conv2D(32, (3,3), activation='relu')(inputs)
    x = MaxPooling2D(2,2)(x)
    x = Conv2D(64, (3,3), activation='relu')(x)
    x = MaxPooling2D(2,2)(x)
    x = Conv2D(64, (3,3), activation='relu')(x)
    x = MaxPooling2D(2,2)(x)
    x = Flatten()(x)
    x = Dense(64, activation='relu')(x)
    x = Dropout(0.2)(x)
    outputs = Dense(num_classes, activation='softmax')(x)
    return tf.keras.Model(inputs=inputs, outputs=outputs)

def create_deep_model(input_shape, num_classes):
    base_model = ResNet50V2(
        weights='imagenet',
        include_top=False,
        input_shape=input_shape
    )
    
    fine_tune_at = 100
    for layer in base_model.layers[:fine_tune_at]:
        layer.trainable = False

    inputs = tf.keras.Input(shape=input_shape)
    x = base_model(inputs, training=False)
    x = GlobalAveragePooling2D()(x)
    x = BatchNormalization()(x)
    x = Dense(512, activation='relu')(x)
    x = Dropout(0.5)(x)
    x = BatchNormalization()(x)
    x = Dense(256, activation='relu')(x)
    x = Dropout(0.3)(x)
    outputs = Dense(num_classes, activation='softmax')(x)
    return tf.keras.Model(inputs=inputs, outputs=outputs)

if check_and_download_images():
    print("\nProceeding with training...\n")

dataset_dir = 'dataset'
train_dir = os.path.join(dataset_dir, 'train')
val_dir = os.path.join(dataset_dir, 'val')

try:
    num_classes, class_names = get_num_classes(train_dir, val_dir)
    print(f"Found {num_classes} matching classes: {class_names}")
    
    print("\nSelect training mode:")
    print("1. Light Training (Faster, less accurate)")
    print("2. Deep Training (Slower, more accurate)")
    
    while True:
        mode = input("\nEnter your choice (1-2): ").strip()
        if mode in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    train_datagen = ImageDataGenerator(
        rescale=1./255,
        rotation_range=40,
        width_shift_range=0.2,
        height_shift_range=0.2,
        shear_range=0.2,
        zoom_range=0.2,
        horizontal_flip=True,
        fill_mode='nearest',
        brightness_range=[0.7, 1.3],
        validation_split=0.1
    )

    val_datagen = ImageDataGenerator(rescale=1./255)

    IMG_SIZE = 224 if mode == '2' else 150
    BATCH_SIZE = 16 if mode == '2' else 32
    EPOCHS = 50 if mode == '2' else 20

    train_generator = train_datagen.flow_from_directory(
        train_dir,
        target_size=(IMG_SIZE, IMG_SIZE),
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        classes=class_names,
        shuffle=True,
        seed=42,
        subset=None
    )

    val_generator = val_datagen.flow_from_directory(
        val_dir,
        target_size=(IMG_SIZE, IMG_SIZE),
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        classes=class_names,
        shuffle=False,
        seed=42
    )

    input_shape = (IMG_SIZE, IMG_SIZE, 3)
    model = create_deep_model(input_shape, num_classes) if mode == '2' else create_light_model(input_shape, num_classes)
    
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.0001 if mode == '2' else 0.001),
        loss='categorical_crossentropy',
        metrics=['accuracy', tf.keras.metrics.TopKCategoricalAccuracy(k=3, name='top_3_accuracy')]
    )

    print("\nEarly stopping configuration:")
    use_early_stopping = input("Do you want to enable early stopping? (y/n): ").lower().strip() == 'y'
    
    callbacks = []
    
    if use_early_stopping:
        patience = 5 if mode == '2' else 3
        print(f"\nModel will stop training if validation loss doesn't improve for {patience} epochs")
        callbacks.append(
            EarlyStopping(
                monitor='val_loss',
                patience=patience,
                restore_best_weights=True,
                verbose=1  # Add verbosity to show when early stopping triggers
            )
        )
    
    callbacks.append(
        ModelCheckpoint(
            'titano-N1_best_model.h5',
            monitor='val_accuracy',
            save_best_only=True,
            mode='max',
            verbose=1  # Add verbosity to show when best model is saved
        )
    )

    print(f"\nStarting training for {EPOCHS} epochs (may stop earlier if early stopping is enabled)")
    
    history = model.fit(
        train_generator,
        epochs=EPOCHS,
        validation_data=val_generator,
        callbacks=callbacks,
        verbose=1
    )

    # At the end of training, print summary
    actual_epochs = len(history.history['loss'])
    if actual_epochs < EPOCHS:
        print(f"\nTraining stopped early at epoch {actual_epochs}/{EPOCHS}")
        print("Reason: Validation loss stopped improving")

    model.save('titano-N1.h5')
    
    # Save model configuration
    model_config = {
        'input_shape': [IMG_SIZE, IMG_SIZE],
        'mode': 'deep' if mode == '2' else 'light',
        'class_names': class_names
    }
    
    with open('titano-N1_config.json', 'w') as f:
        json.dump(model_config, f)
    
    with open('titano-N1_class_names.json', 'w') as f:
        json.dump(class_names, f)
    
    print("Model saved as 'titano-N1.h5'")
    print("Model configuration saved as 'titano-N1_config.json'")
    print("Class names saved as 'titano-N1_class_names.json'")

    plt.figure(figsize=(15, 5))
    
    plt.subplot(1, 3, 1)
    plt.plot(history.history['accuracy'], label='Training Accuracy')
    plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
    plt.title('Model Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()
    
    plt.subplot(1, 3, 2)
    plt.plot(history.history['loss'], label='Training Loss')
    plt.plot(history.history['val_loss'], label='Validation Loss')
    plt.title('Model Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    
    plt.subplot(1, 3, 3)
    plt.plot(history.history['top_3_accuracy'], label='Top 3 Accuracy')
    plt.plot(history.history['val_top_3_accuracy'], label='Validation Top 3')
    plt.title('Top 3 Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()
    
    plt.tight_layout()
    plt.show()

except Exception as e:
    print(f"Error during training: {e}")