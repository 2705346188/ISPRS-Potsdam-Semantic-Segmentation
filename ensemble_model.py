# -*- coding: utf-8 -*-
"""
Created on Sat Aug 31 17:11:52 2019

@author: Aidan
"""

import os
import random

import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from keras.applications import ResNet50
from keras.models import Model
from keras.layers import Input, BatchNormalization, Activation, Dropout, Average, Lambda, Add, Reshape, Convolution2D
from keras.layers.convolutional import Conv2D, Conv2DTranspose
from keras.layers.pooling import MaxPooling2D
from keras.layers.merge import concatenate
from keras.optimizers import Adam
from skimage.io import imread
import tifffile as tiff

plt.style.use("ggplot")

BATCH_SIZE = 4


def data_gen(img_folder, mask_folder, batch_size):
    c = 0
    n = os.listdir(img_folder)
    o = os.listdir(mask_folder)

    while True:
        img = np.zeros((batch_size, 160, 160, 3)).astype("float")
        mask = np.zeros((batch_size, 160, 160, 6)).astype("bool")

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
test_mask_path = "data2/test_labels"

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


num_classes = 6
im_height = 160
im_width = 160

input_tensor = Input((im_height, im_width, 3))

base_model = ResNet50(include_top=False, weights="imagenet",
                      input_tensor=input_tensor)

x32 = base_model.get_layer("add_16").output
x16 = base_model.get_layer("add_13").output
x8 = base_model.get_layer("add_7").output

c32 = Convolution2D(num_classes, (1, 1))(x32)
c16 = Convolution2D(num_classes, (1, 1))(x16)
c8 = Convolution2D(num_classes, (1, 1))(x8)


def resize_bilinear(images):
    return tf.image.resize_bilinear(images, [im_height, im_width])


r32 = Lambda(resize_bilinear)(c32)
r16 = Lambda(resize_bilinear)(c16)
r8 = Lambda(resize_bilinear)(c8)

m = Add()([r32, r16, r8])

x = Reshape((im_height * im_width, num_classes))(m)
x = Activation("softmax")(x)
x = Reshape((im_height, im_width, num_classes))(x)

fcn_model = Model(input=input_tensor, outputs=x)

fcn_model.compile(optimizer=Adam(), loss="categorical_crossentropy",
                  metrics=["accuracy"])

print(fcn_model.summary())

fcn_model.load_weights("deeplab-weights-50.h5")


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

    outputs = Conv2D(num_classes, (1, 1), activation="softmax")(c9)
    model = Model(inputs=[input_img], outputs=[outputs])
    return model


input_img = Input(shape=(im_height, im_width, 3), name="img")
model = get_unet(input_tensor, n_filters=16, dropout=0.05, batchnorm=True)

print(model.summary())

model.compile(optimizer=Adam(),
              loss="categorical_crossentropy",
              metrics=["acc"])

model.load_weights("segmentation-model1.h5")

models = [fcn_model, model]


def ensemble(models, model_input):
    outputs = [model.outputs[0] for model in models]
    y = Average()(outputs)
    model = Model(model_input, y, name="ensemble")
    return model


ensemble_model = ensemble(models, input_tensor)

#X = imread("data2/image_data/train_data1.png").reshape(1, 160, 160, 3)/255.
#y = tiff.imread("labels2/image_labels/train_labels1.tif").reshape(1, 160, 160, 6)
X = np.load("data/final_train_data1.npy")
y = np.load("labels/final_train_labels1.npy")

#preds_train_1 = model.predict(X, verbose=True)
#preds_train_2 = fcn_model.predict(X, verbose=True)
preds_train = ensemble_model.predict(X, verbose=True)
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

    plt.show()

    # cars = yellow
    true_cars_overlay = (y[ix, ..., 0] > 0).reshape(im_height, im_width, 1)
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 0.5), axis=2)
    # buildings = blue
    true_buildings_overlay = (y[ix, ..., 1] > 0).reshape(im_height, im_width, 1)
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 0.5), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (y[ix, ..., 2] > 0).reshape(im_height, im_width, 1)
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 0.5), axis=2)
    # trees = green
    true_trees_overlay = (y[ix, ..., 3] > 0).reshape(im_height, im_width, 1)
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 0.5), axis=2)
    # impervious = white
    true_impervious_overlay = (y[ix, ..., 4] > 0).reshape(im_height, im_width, 1)
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 0.5), axis=2)
    # clutter = red
    true_clutter_overlay = (y[ix, ..., 5] > 0).reshape(im_height, im_width, 1)
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
    plt.show()

    # cars = yellow
    true_cars_overlay = (binary_preds[ix, ..., 0] > 0).reshape(im_height, im_width, 1)
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay * 0.5), axis=2)
    # buildings = blue
    true_buildings_overlay = (binary_preds[ix, ..., 1] > 0).reshape(im_height, im_width, 1)
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay * 0.5), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (binary_preds[ix, ..., 2] > 0).reshape(im_height, im_width, 1)
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay * 0.5), axis=2)
    # trees = green
    true_trees_overlay = (binary_preds[ix, ..., 3] > 0).reshape(im_height, im_width, 1)
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay * 0.5), axis=2)
    # impervious = white
    true_impervious_overlay = (binary_preds[ix, ..., 4] > 0).reshape(im_height, im_width, 1)
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay * 0.5), axis=2)
    # clutter = red
    true_clutter_overlay = (binary_preds[ix, ..., 5] > 0).reshape(im_height, im_width, 1)
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
    plt.show()


#plot_sample(X, y, preds_train, preds_train_t, ix=0)


def plot_labels(X, y, preds):
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

    '''
    fig, ax = plt.subplots(1, 1, figsize=(20, 20))
    ax.imshow(image_array, interpolation="bilinear")
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.savefig("image6.png", bbox_inches="tight")
    plt.show()
    '''

    # cars = yellow
    true_cars_overlay = (labels_array[..., 0] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay), axis=2)
    # buildings = blue
    true_buildings_overlay = (labels_array[..., 1] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (labels_array[..., 2] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay), axis=2)
    # trees = green
    true_trees_overlay = (labels_array[..., 3] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay), axis=2)
    # impervious = white
    true_impervious_overlay = (labels_array[..., 4] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay), axis=2).astype(int)
    # clutter = red
    true_clutter_overlay = (labels_array[..., 5] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay), axis=2)

    fig, ax = plt.subplots(2, 1, figsize=(20, 20))
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
    true_cars_overlay_rgba = np.concatenate((true_cars_overlay, true_cars_overlay, np.zeros(true_cars_overlay.shape), true_cars_overlay), axis=2)
    # buildings = blue
    true_buildings_overlay = (preds_array[..., 1] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_buildings_overlay_rgba = np.concatenate((np.zeros(true_buildings_overlay.shape), np.zeros(true_buildings_overlay.shape), true_buildings_overlay, true_buildings_overlay), axis=2)
    # low_vegetation = cyan
    true_low_vegetation_overlay = (preds_array[..., 2] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_low_vegetation_overlay_rgba = np.concatenate((np.zeros(true_low_vegetation_overlay.shape), true_low_vegetation_overlay, true_low_vegetation_overlay, true_low_vegetation_overlay), axis=2)
    # trees = green
    true_trees_overlay = (preds_array[..., 3] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_trees_overlay_rgba = np.concatenate((np.zeros(true_trees_overlay.shape), true_trees_overlay, np.zeros(true_trees_overlay.shape), true_trees_overlay), axis=2)
    # impervious = white
    true_impervious_overlay = (preds_array[..., 4] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_impervious_overlay_rgba = np.concatenate((true_impervious_overlay, true_impervious_overlay, true_impervious_overlay, true_impervious_overlay), axis=2).astype(int)
    # clutter = red
    true_clutter_overlay = (preds_array[..., 5] > 0).reshape((width*(160-14)+14, height*(160-14)+14, 1))
    true_clutter_overlay_rgba = np.concatenate((true_clutter_overlay, np.zeros(true_clutter_overlay.shape), np.zeros(true_clutter_overlay.shape), true_clutter_overlay), axis=2)

    ax[1].imshow(true_cars_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_buildings_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_low_vegetation_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_trees_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_impervious_overlay_rgba, interpolation="bilinear")
    ax[1].imshow(true_clutter_overlay_rgba, interpolation="bilinear")
    ax[1].grid(False)
    ax[1].set_xticks([])
    ax[1].set_yticks([])
    plt.savefig("ensemble-labels1.png", bbox_inches="tight")
    plt.show()


plot_labels(X, y, preds_train_t)
