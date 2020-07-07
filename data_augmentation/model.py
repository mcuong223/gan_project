from keras.models import Model, load_model
from keras import applications
import keras.backend as K
import matplotlib.pyplot as plt

import keras
from keras_contrib.applications.resnet import ResNet, basic_block
from keras_contrib.applications.densenet import DenseNet
import keras.applications as k_apps
from keras.layers import (
    Input, Dense, Reshape,
    Flatten, Embedding, Dropout,
    BatchNormalization, Activation,
    Lambda,Layer, Add, Concatenate,
    Average,GlobalAveragePooling2D,
    MaxPooling2D, AveragePooling2D,
)
from keras.layers.convolutional import (
    UpSampling2D,
    Conv2D, Conv2DTranspose
)
from keras.optimizers import Adam, SGD

from keras.utils import to_categorical
import tensorflow as tf
import numpy as np
import keras.preprocessing.image as iprocess

class Option:
    gan_v1 = 1
    gan_v2 = 2
    bagan = 3
    vgg16 = 4
    vgg16_st_aug = 5

def plot_history(history):
    # plot acc
    loss, val_loss, acc, val_acc = history['main_out_loss'], \
                                   history['val_main_out_loss'], \
                                   history['main_out_accuracy'], \
                                   history['val_main_out_accuracy']
    plt.plot(acc, label='train')
    plt.plot(val_acc, label='val')
    plt.ylabel('acc')
    plt.xlabel('epoch')
    plt.title('Training accuracy')
    plt.legend()
    plt.show()
    # plot loss
    plt.plot(loss, label='train')
    plt.plot(val_loss, label='val')
    plt.ylabel('loss')
    plt.xlabel('epoch')
    plt.title('Training loss')
    plt.legend()
    plt.show()

def flatten_model(model_nested):
    layers_flat = []
    for layer in model_nested.layers:
        try:
            layers_flat.extend(layer.layers)
        except AttributeError:
            layers_flat.append(layer)

    model_flat = keras.models.Sequential(layers_flat)
    return model_flat

def tran_one(img, d=15):
    degree = np.random.randint(-d, d)
    img = iprocess.random_brightness(img, (0.5, 1.5))
    if np.random.rand() >= 0.5:
       img = np.fliplr(img)
 
    return iprocess.apply_affine_transform(img, degree)

def augment(imgs, labels,plus = 1, target_labels=None):
    if plus == 0:
        return imgs, labels
    if target_labels is None:
        target_labels = np.unique(labels)

    deimgs = imgs *127.5 + 127.5
    imgs_ = []
    labels_ = []
    for i in range(imgs.shape[0]):
        # original
        imgs_.append(deimgs[i])
        labels_.append(labels[i])
        if labels[i] not in target_labels:
            continue

        # Augment
        for j in range(plus):
            imgs_.append(tran_one(deimgs[i]))
            labels_.append(labels[i])

    return ((np.array(imgs_) -127.5) / 127.5), np.array(labels_)


def re_balance(imgs, labels, per_class_samples=None):
    deimgs = imgs *127.5 + 127.5
    imgs_ = []
    labels_ = []
    size = len(np.unique(labels))
    counter = [0] * size
    if per_class_samples is None:
        per_class_samples = [1000] * size

    print(counter)
    print(per_class_samples)
    # original
    for i in range(imgs.shape[0]):
        
        imgs_.append(deimgs[i])
        labels_.append(labels[i])
    # Augment
    for _ in range(1000):
        for i in range(imgs.shape[0]):
            l_idx = labels[i]
            if counter[l_idx] >= per_class_samples[l_idx]:
                counter[l_idx] = -1 # Done
            if counter[l_idx] != -1:
                imgs_.append(tran_one(deimgs[i]))
                labels_.append(l_idx)
                counter[l_idx] += 1

        print(counter)
        print(counter.count(-1), size)
        if counter.count(-1) == size:
            break

    return ((np.array(imgs_) -127.5) / 127.5), np.array(labels_)

def vgg_16_features(image, num_of_classes, dims=64, rst=64, from_scratch=True):
    weights = None if from_scratch else 'imagenet'
    model = k_apps.VGG16(include_top=False,
                        weights=weights,
                        input_tensor=None,
                        input_shape=(rst, rst, 3),
                        pooling='avg',
                        classes=num_of_classes)

    if not from_scratch:
        for layer in model.layers:
            accept_name = ['block1', 'block2', 'block3', 'block4', 'block5'][:1]
            if any(x in layer.name for x in accept_name):
                layer.trainable = False
            else:
                layer.trainable = True
        x = model(image)
        x = Dense(dims)(x)
        out1 = keras.layers.advanced_activations.PReLU(name='side_out')(x)
        out2 = Dense(num_of_classes, activation='softmax', name='main_out')(out1)
        return out1, out2
    else:
        x = model(image)
        x1 = Dense(dims)(x)
        out1 = keras.layers.advanced_activations.PReLU(name='side_out')(x1)
        out2 = Dense(num_of_classes, activation='softmax', name='main_out')(x)
        return out1, out2

def main_model(num_of_classes, rst=64, feat_dims=128, lr=1e-5, loss_weights=[1, 0.1],
                from_scratch=True):
    image = Input((rst, rst, 3))
    labels = Input((1,))
    side_output, final_output = vgg_16_features(image, num_of_classes, feat_dims, rst,from_scratch)
    centers = Embedding(num_of_classes, feat_dims)(labels)
    l2_loss = Lambda(lambda x: K.sum(K.square(x[0]-x[1][:,0]),1,keepdims=True),
                        name='l2_loss')([side_output ,centers])

    labels_plus_embeddings = Concatenate()([labels, side_output])
    train_model = Model(inputs=[image, labels],
                        # outputs=labels_plus_embeddings,
                        outputs=[final_output, l2_loss]
                        )
    train_model.compile(optimizer=Adam(lr),
                        loss=["categorical_crossentropy",lambda y_true,y_pred: y_pred],
                        # loss = triplet_loss_adapted_from_tf,
                        loss_weights=loss_weights,
                        metrics=['accuracy'])

    return train_model


def l2_distance(a, b):
    return np.mean(np.square(a - b))

def cosine_sim(a, b):
    return - (np.dot(a, b)/(np.linalg.norm(a)*np.linalg.norm(b)))

def cal_sp_vectors(embbeder, supports,k_shot):
    means = []
    x_sp, y_sp = supports
    classes = np.unique(y_sp)
    # perclassid
    per_class_ids = dict()
    ids = np.array(range(len(x_sp)))
    for c in classes:
        per_class_ids[c] = ids[y_sp == c]

    for c in classes:
        imgs = x_sp[per_class_ids[c][:k_shot]]
        # imgs = utils.triple_channels(imgs)
        latent = embbeder.predict(imgs)
        means.append(np.mean(latent, axis=0))
    return np.array(means)
    
def classify_by_metric(embbeder, supports, images, k_shot=1,metric='l2'):
    x_sp, y_sp = supports
    classes = np.unique(y_sp)
    # currently do one-shot classification
    sp_vectors = cal_sp_vectors(embbeder, supports,k_shot)
    vectors = embbeder.predict(triple_channels(images))
    metric_func = l2_distance if metric == 'l2' else cosine_sim
    similiarity = np.array([metric_func(vector, sp_vector) \
                        for vector in vectors \
                        for sp_vector in sp_vectors]).reshape(-1, len(classes))
    pred = np.argmin(np.array(similiarity), axis=1)
    return pred

def evaluate_by_metric(embbeder, supports, images, labels, k_shot=1,metric='l2'):
    pred = classify_by_metric(embbeder, supports,
                              images,k_shot=k_shot, metric=metric)
    acc = (pred == labels).mean()
    return acc
