# -*- coding: utf-8 -*-
"""
Created on Thu Jul 18 07:42:01 2019

@author: Aidan
"""

import os
import random
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import tensorflow as tf
from keras.models import Model
from keras.layers import Input, BatchNormalization, Activation, Dropout
from keras.layers.convolutional import Conv2D, Conv2DTranspose
from keras.layers.pooling import MaxPooling2D
from keras.layers.merge import concatenate
from keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from keras.optimizers import Adam
from skimage.io import imread
import tifffile as tiff

# Use this to allow GPU server to create graphs
matplotlib.use("Agg")
plt.style.use("ggplot")

# Used for GPU server to select specific GPU
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

# Batch size should be as big as can be handled by computer, up to 32
BATCH_SIZE = 8
NUM_CLASSES = 6
IM_HEIGHT = 160
IM_WIDTH = 160


def data_gen(img_folder, mask_folder, batch_size):
    c = 0
    # IMPORTANT for linux OS to sort folders
    n = sorted(os.listdir(img_folder))
    o = sorted(os.listdir(mask_folder))

    while True:
        # Initialise the image and mask arrays
        img = np.zeros((batch_size, 160, 160, 3)).astype("float")
        mask = np.zeros((batch_size, 160, 160, 6)).astype("bool")

        # Create a generator that makes batches of batch_size
        for i in range(c, c+batch_size):
            train_img = imread(img_folder+"/"+n[i])/255.
            img[i-c] = train_img
            train_mask = tiff.imread(mask_folder+"/"+o[i])
            mask[i-c] = train_mask

        c += batch_size
        if (c+batch_size >= len(os.listdir(img_folder))):
            c = 0

        yield img, mask


train_frame_path = "data2/image_data"
train_mask_path = "labels2/image_labels"

val_frame_path = "data2/val_data"
val_mask_path = "labels2/val_labels"

test_frame_path = "data2/test_data"
test_mask_path = "labels2/test_labels"

# Create data generators for the train, validation, and test sets
train_gen = data_gen(train_frame_path, train_mask_path, batch_size=BATCH_SIZE)
val_gen = data_gen(val_frame_path, val_mask_path, batch_size=BATCH_SIZE)
test_gen = data_gen(test_frame_path, test_mask_path, batch_size=BATCH_SIZE)


def conv2d_block(input_tensor, n_filters, kernel_size=3, batchnorm=True):
    # first layers
    x = Conv2D(filters=n_filters, kernel_size=(kernel_size, kernel_size),
               kernel_initializer="he_normal", padding="same")(input_tensor)
    if batchnorm:
        x = BatchNormalization()(x)
    x = Activation("relu")(x)
    # second layer
    x = Conv2D(filters=n_filters, kernel_size=(kernel_size, kernel_size),
               kernel_initializer="he_normal", padding="same")(x)
    if batchnorm:
        x = BatchNormalization()(x)
    x = Activation("relu")(x)
    return x


def get_unet(input_img, n_filters=16, dropout=0.5, batchnorm=True):
    # contracting path
    c1 = conv2d_block(input_img, n_filters=n_filters * 1, kernel_size=3,
                      batchnorm=batchnorm)
    p1 = MaxPooling2D((2, 2))(c1)
    p1 = Dropout(dropout * 0.5)(p1)

    c2 = conv2d_block(p1, n_filters=n_filters * 2, kernel_size=3,
                      batchnorm=batchnorm)
    p2 = MaxPooling2D((2, 2))(c2)
    p2 = Dropout(dropout)(p2)

    c3 = conv2d_block(p2, n_filters=n_filters * 4, kernel_size=3,
                      batchnorm=batchnorm)
    p3 = MaxPooling2D((2, 2))(c3)
    p3 = Dropout(dropout)(p3)

    c4 = conv2d_block(p3, n_filters=n_filters * 8, kernel_size=3,
                      batchnorm=batchnorm)
    p4 = MaxPooling2D((2, 2))(c4)
    p4 = Dropout(dropout)(p4)

    c5 = conv2d_block(p4, n_filters=n_filters * 16, kernel_size=3,
                      batchnorm=batchnorm)

    # expansive path
    u6 = Conv2DTranspose(n_filters * 8, (3, 3), strides=(2, 2),
                         padding="same")(c5)
    u6 = concatenate([u6, c4])
    u6 = Dropout(dropout)(u6)
    c6 = conv2d_block(u6, n_filters=n_filters * 8, kernel_size=3,
                      batchnorm=batchnorm)

    u7 = Conv2DTranspose(n_filters * 4, (3, 3), strides=(2, 2),
                         padding="same")(c6)
    u7 = concatenate([u7, c3])
    u7 = Dropout(dropout)(u7)
    c7 = conv2d_block(u7, n_filters=n_filters * 4, kernel_size=3,
                      batchnorm=batchnorm)

    u8 = Conv2DTranspose(n_filters * 2, (3, 3), strides=(2, 2),
                         padding="same")(c7)
    u8 = concatenate([u8, c2])
    u8 = Dropout(dropout)(u8)
    c8 = conv2d_block(u8, n_filters=n_filters * 2, kernel_size=3,
                      batchnorm=batchnorm)

    u9 = Conv2DTranspose(n_filters * 1, (3, 3), strides=(2, 2),
                         padding="same")(c8)
    u9 = concatenate([u9, c1], axis=3)
    u9 = Dropout(dropout)(u9)
    c9 = conv2d_block(u9, n_filters=n_filters * 1, kernel_size=3,
                      batchnorm=batchnorm)

    outputs = Conv2D(NUM_CLASSES, (1, 1), activation="softmax")(c9)
    model = Model(inputs=[input_img], outputs=[outputs])
    return model


input_img = Input(shape=(IM_HEIGHT, IM_WIDTH, 3), name="img")
model = get_unet(input_img, n_filters=16, dropout=0.05, batchnorm=True)

print(model.summary())

model.compile(optimizer=Adam(lr=0.001),
              loss="categorical_crossentropy",
              metrics=["acc"])

#model.load_weights("unet-model-checkpoint.h5")

callbacks = [EarlyStopping(patience=10, verbose=True),
             ReduceLROnPlateau(factor=0.1, patience=5, min_lr=0.0000001,
                               verbose=True),
             ModelCheckpoint("unet-model-checkpoint.h5", save_best_only=True,
                             save_weights_only=True)]

num_training_samples = 30888
num_validation_samples = 4612
num_test_samples = 5043
num_epochs = 100
results = model.fit_generator(generator=train_gen,
                              steps_per_epoch=num_training_samples//BATCH_SIZE,
                              epochs=num_epochs, callbacks=callbacks,
                              validation_data=val_gen,
                              validation_steps=num_validation_samples//BATCH_SIZE,
                              verbose=1)

# Save last model
model.save_weights("unet-model-{}.h5".format(num_epochs))

plt.figure(figsize=(8, 8))
plt.title("Learning curve")
plt.plot(results.history["loss"], label="loss")
plt.plot(results.history["val_loss"], label="val_loss")
plt.plot(np.argmin(results.history["val_loss"]),
         np.min(results.history["val_loss"]), marker='x', color='r',
         label="best model")
plt.xlabel("Epochs")
plt.ylabel("log_loss")
plt.legend()
plt.savefig("lossplot-unet-{}.png".format(num_epochs), bbox_inches="tight")
plt.show()

plt.figure(figsize=(8, 8))
plt.title("Accuracy curve")
plt.plot(results.history["acc"], label="acc")
plt.plot(results.history["val_acc"], label="val_acc")
plt.plot(np.argmax(results.history["val_acc"]),
         np.max(results.history["val_acc"]), marker='x', color='r',
         label="best model")
plt.xlabel("Epochs")
plt.ylabel("acc")
plt.legend()
plt.savefig("accplot-unet-{}.png".format(num_epochs), bbox_inches="tight")
plt.show()

test_loss, test_acc = model.evaluate_generator(generator=test_gen,
                                               steps=num_test_samples,
                                               verbose=1)
print("\n")
print("Test acc: ", test_acc)
print("Test loss: ", test_loss)

# Find the F1 scores of each class
X_test = np.concatenate((
        np.load("data/final_train_data7.npy"),
        np.load("data/final_train_data15.npy"),
        np.load("data/final_train_data23.npy")), axis=0)
y_test = np.concatenate((
        np.load("labels/final_train_labels7.npy"),
        np.load("labels/final_train_labels15.npy"),
        np.load("labels/final_train_labels23.npy")), axis=0)
Y_test = np.argmax(y_test, axis=3).flatten()
y_pred = model.predict(X_test)
Y_pred = np.argmax(y_pred, axis=3).flatten()
correct = np.zeros((6))
totals1 = np.zeros((6))
totals2 = np.zeros((6))

for i in range(len(Y_test)):
    if Y_pred[i] == Y_test[i]:
        correct[Y_pred[i]] += 1
    totals1[Y_pred[i]] += 1
    totals2[Y_test[i]] += 1

precision = correct / totals1
recall = correct / totals2
F1 = 2 * (precision*recall) / (precision + recall)
print(F1)

# Load image and labels to create mask
X = imread("data2/image_data/train_data0.png").reshape(1, 160, 160, 3)/255.
y = tiff.imread("labels2/image_labels/train_labels0.tif").reshape(1, 160, 160, 6)

preds_train = model.predict(X, verbose=True)
preds_train_t = (preds_train == preds_train.max(axis=3)[..., None]).astype(int)


def plot_sample(X, y, preds, binary_preds, ix=None):
    if ix is None:
        ix = random.randint(0, len(X))
        print("ix:", ix)

    fig, ax = plt.subplots(13, 1, figsize=(10, 20))

    ax[0].imshow(X[ix], interpolation="bilinear")
    ax[0].set_title("Picture")

    for i in range(6):
        ax[2 * i + 1].imshow(y[ix, ..., i], interpolation="bilinear",
                             cmap="gray")
        ax[2 * i + 1].set_title("True Label")

        ax[2 * i + 2].imshow(preds[ix, ..., i], interpolation="bilinear",
                             cmap="gray")
        ax[2 * i + 2].set_title("Predicted Label")

    plt.savefig("image_unet{}.png".format(ix), bbox_inches="tight")
    #plt.show()

    # cars = yellow
    true_cars_overlay = (y[ix, ..., 0] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 0.5), axis=2)
    # buildings = blue
    true_buildings_overlay = (y[ix, ..., 1] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 0.5), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (y[ix, ..., 2] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 0.5), axis=2)
    # trees = green
    true_trees_overlay = (y[ix, ..., 3] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 0.5), axis=2)
    # impervious = white
    true_impervious_overlay = (y[ix, ..., 4] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 0.5), axis=2)
    # clutter = red
    true_clutter_overlay = (y[ix, ..., 5] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay * 0.5), axis=2)

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(X[ix], interpolation="bilinear")
    ax.imshow(true_cars_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_buildings_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_low_vegetation_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_trees_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_impervious_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_clutter_overlay_rgba, interpolation="bilinear")
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.savefig("true_labels_unet_200_{}".format(ix), bbox_inches="tight")
    plt.show()

    # cars = yellow
    true_cars_overlay = (binary_preds[ix, ..., 0] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 0.5), axis=2)
    # buildings = blue
    true_buildings_overlay = (binary_preds[ix, ..., 1] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 0.5), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (binary_preds[ix, ..., 2] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 0.5), axis=2)
    # trees = green
    true_trees_overlay = (binary_preds[ix, ..., 3] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 0.5), axis=2)
    # impervious = white
    true_impervious_overlay = (binary_preds[ix, ..., 4] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 0.5), axis=2)
    # clutter = red
    true_clutter_overlay = (binary_preds[ix, ..., 5] > 0).reshape(IM_HEIGHT, IM_WIDTH, 1)
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay * 0.5), axis=2)

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(X[ix], interpolation="bilinear")
    ax.imshow(true_cars_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_buildings_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_low_vegetation_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_trees_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_impervious_overlay_rgba, interpolation="bilinear")
    ax.imshow(true_clutter_overlay_rgba, interpolation="bilinear")
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.savefig("predicted_labels_unet_200_{}.png".format(ix), bbox_inches="tight")
    plt.show()


for i in range(1):
    plot_sample(X, y, preds_train, preds_train_t, ix=i)


def plot_image(X, y, preds):
    width = 41
    height = 41
    image_array = np.zeros((width*160-(width-1)*14, height*160-(height-1)*14, 3), dtype=np.int)
    labels_array = np.zeros((width*160-(width-1)*14, height*160-(height-1)*14, 6), dtype=np.bool)
    preds_array = np.zeros((width*160-(width-1)*14, height*160-(height-1)*14, 6))
    for i in range(width):
        for j in range(height):
            image_array[i*(160-14):(i+1)*(160-14)+14, j*(160-14):(j+1)*(160-14)+14, :] = X[i*41+j]
            labels_array[i*(160-14):(i+1)*(160-14)+14, j*(160-14):(j+1)*(160-14)+14, :] = y[i*41+j]
            preds_array[i*(160-14):i*(160-14)+14, j*(160-14):(j+1)*(160-14)+14, :] += preds[i*41+j, :14, :, :]
            preds_array[i*(160-14):(i+1)*(160-14)+14, j*(160-14):j*(160-14)+14, :] += preds[i*41+j, :, :14, :]
            preds_array[i*(160-14)+14:(i+1)*(160-14)+14, j*(160-14)+14:(j+1)*(160-14)+14, :] += preds[i*41+j, 14:, 14:, :]

    # cars = yellow
    true_cars_overlay = (labels_array[..., 0] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 1.0), axis=2)
    # buildings = blue
    true_buildings_overlay = (labels_array[..., 1] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 01.), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (labels_array[..., 2] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 1.0), axis=2)
    # trees = green
    true_trees_overlay = (labels_array[..., 3] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 1.0), axis=2)
    # impervious = white
    true_impervious_overlay = (labels_array[..., 4] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 1.0), axis=2)
    # clutter = red
    true_clutter_overlay = (labels_array[..., 5] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay * 1.0), axis=2)

    fig, ax = plt.subplots(2, 1, figsize=(20, 20))
    ax[0].imshow(image_array, interpolation="bilinear")
    ax[0].imshow(true_cars_overlay_rgba, interpolation="bilinear")
    ax[0].imshow(true_buildings_overlay_rgba, interpolation="bilinear")
    ax[0].imshow(true_low_vegetation_overlay_rgba, interpolation="bilinear")
    ax[0].imshow(true_trees_overlay_rgba, interpolation="bilinear")
    ax[0].imshow(true_impervious_overlay_rgba, interpolation="bilinear")
    ax[0].imshow(true_clutter_overlay_rgba, interpolation="bilinear")
    ax[0].grid(False)
    ax[0].set_xticks([])
    ax[0].set_yticks([])

    # cars = yellow
    true_cars_overlay = (preds_array[..., 0] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 1.0), axis=2)
    # buildings = blue
    true_buildings_overlay = (preds_array[..., 1] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 1.0), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (preds_array[..., 2] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 1.0), axis=2)
    # trees = green
    true_trees_overlay = (preds_array[..., 3] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 1.0), axis=2)
    # impervious = white
    true_impervious_overlay = (preds_array[..., 4] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 1.0), axis=2)
    # clutter = red
    true_clutter_overlay = (preds_array[..., 5] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay * 1.0), axis=2)

    ax[1].imshow(image_array, interpolation="bilinear")
    ax[1].imshow(true_cars_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_buildings_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_low_vegetation_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_trees_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_impervious_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_clutter_overlay_rgba, interpolation="bilinear")
    ax[1].grid(False)
    ax[1].set_xticks([])
    ax[1].set_yticks([])
    plt.savefig("deeplab200image0.png", bbox_inches="tight")
    plt.show()


plot_image(X, y, preds_train_t)
