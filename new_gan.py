
import csv
from collections import defaultdict
import keras.backend as K
import tensorflow as tf

from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import (
    UpSampling2D, Convolution2D,
    Conv2D, Conv2DTranspose
)
from keras.models import Sequential, Model, model_from_json
from keras.optimizers import Adam
from keras.losses import mean_squared_error, cosine_similarity
from keras.layers import (
    Input, Dense, Reshape,
    Flatten, Embedding, Dropout,
    BatchNormalization, Activation,
    Lambda,Layer, Add, Concatenate,
    Average,GaussianNoise,
    MaxPooling2D, AveragePooling2D
)

from keras.applications.vgg16 import VGG16

from keras.utils import np_utils
import sklearn.metrics as metrics
from sklearn.model_selection import train_test_split
from mlxtend.plotting import plot_confusion_matrix
import matplotlib.pyplot as plt

import os
import sys
import re
import numpy as np
import datetime
import pickle
import cv2

from google.colab.patches import cv2_imshow
from PIL import Image

DS_DIR = '/content/drive/My Drive/bagan/dataset/chest_xray'
DS_SAVE_DIR = '/content/drive/My Drive/bagan/dataset/save'
CLASSIFIER_DIR = '/content/drive/My Drive/chestxray_classifier'


def save_image_array(img_array, fname=None, show=None):
        # convert 1 channel to 3 channels
        channels = img_array.shape[-1]
        resolution = img_array.shape[2]
        img_rows = img_array.shape[0]
        img_cols = img_array.shape[1]

        img = np.full([resolution * img_rows, resolution * img_cols, channels], 0.0)
        for r in range(img_rows):
            for c in range(img_cols):
                img[
                (resolution * r): (resolution * (r + 1)),
                (resolution * (c % 10)): (resolution * ((c % 10) + 1)),
                :] = img_array[r, c]

        img = (img * 127.5 + 127.5).astype(np.uint8)
        if show:
            try:
                cv2_imshow(img)
            except Exception as e:
                fname = '/content/drive/My Drive/bagan/result/model_{}/img_{}.png'.format(
                    resolution,
                    datetime.datetime.now().strftime("%m/%d/%Y-%H%M%S")
                )
                print('[show fail] ', str(e))
        if fname:
            try:
                Image.fromarray(img).save(fname)
            except Exception as e:
                print('Save image failed', str(e))


def show_samples(img_array):
    shape = img_array.shape
    img_samples = img_array.reshape(
        (-1, shape[-4], shape[-3], shape[-2], shape[-1])
    )
    save_image_array(img_samples, None, True)

def triple_channels(image):
    # axis = 2 for single image, 3 for many images
    return np.repeat(image, 3, axis = -1)


def load_classifier(rst=256):
    json_file = open(CLASSIFIER_DIR + '/{}/model.json'.format(rst), 'r')
    model = json_file.read()
    json_file.close()
    model = model_from_json(model)
    # load weights into new model
    model.load_weights(CLASSIFIER_DIR + '/{}/weights.h5'.format(rst))
    return model

def pickle_save(object, path):
    try:
        print('save data to {} successfully'.format(path))
        with open(path, "wb") as f:
            return pickle.dump(object, f)
    except:
        print('save data to {} failed'.format(path))



def pickle_load(path):
    try:
        print('load data from {} successfully'.format(path))
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        print(str(e))
        return None

def add_padding(img):
    w, h, _ = img.shape
    size = abs(w - h) // 2
    value= [0, 0, 0]
    if w < h:
        return cv2.copyMakeBorder(img, size, size, 0, 0,
                                    cv2.BORDER_CONSTANT,
                                    value=value)
    return cv2.copyMakeBorder(img, 0, 0, size, size,
                                    cv2.BORDER_CONSTANT,
                                    value=value)

def save_ds(imgs, rst, opt):
    path = '{}/imgs_{}_{}.pkl'.format(DS_SAVE_DIR, opt, rst)
    pickle_save(imgs, path)

def load_ds(rst, opt):
    path = '{}/imgs_{}_{}.pkl'.format(DS_SAVE_DIR, opt, rst)
    return pickle_load(path)

def get_img(path, rst):
    img = cv2.imread(path)
    img = add_padding(img)
    img = cv2.resize(img, (rst, rst))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return np.expand_dims(img, axis=0)
    return img.tolist()

def bound(list, s):
    if s == 0:
        return list
    return list[:s]

def load_train_data(resolution=52):
    labels = []
    i = 0
    res = load_ds(resolution, 'train')
    if res:
        return res

    files =  os.listdir(DS_DIR + '/train/NORMAL')
    imgs = np.array(get_img(DS_DIR + '/train/NORMAL/' + files[0], resolution))
    for file in files[1:]:
        path = DS_DIR + '/train/NORMAL/' + file
        i += 1
        if i % 150 == 0:
            print(len(labels), end=',')
        try:
            imgs = np.concatenate((imgs, get_img(path, resolution)))
            labels.append(0)
        except:
            pass

    files =  os.listdir(DS_DIR + '/train/PNEUMONIA')
    imgs = np.concatenate((imgs,get_img(DS_DIR + '/train/PNEUMONIA/' + files[0], resolution)))
    for file in files[1:]:
        path = DS_DIR + '/train/PNEUMONIA/' + file
        i += 1
        if i % 150 == 0:
            print(len(labels), end=',')
        try:
            imgs = np.concatenate((imgs, get_img(path, resolution)))
            labels.append(1)
        except:
            pass

    res = (np.array(imgs), np.array(labels))
    save_ds(res, resolution, 'train')
    return res

def load_test_data(resolution = 52):
    imgs = []
    labels = []
    res = load_ds(resolution, 'test')
    if res:
        return res
    for file in os.listdir(DS_DIR + '/test/NORMAL'):
        path = DS_DIR + '/test/NORMAL/' + file
        try:
            imgs.append(get_img(path, resolution))
            labels.append(0)
        except:
            pass

    for file in os.listdir(DS_DIR + '/test/PNEUMONIA'):
        path = DS_DIR + '/test/PNEUMONIA/' + file
        try:
            imgs.append(get_img(path, resolution))
            labels.append(1)
        except:
            pass
    res = (np.array(imgs), np.array(labels))
    save_ds(res, resolution, 'test')
    return res

class BatchGenerator:
    TRAIN = 1
    TEST = 0

    def __init__(
        self,
        data_src,
        batch_size=5,
        dataset='MNIST',
        rst=64,
        prune_classes=None,
    ):
        self.batch_size = batch_size
        self.data_src = data_src
        if self.data_src == self.TEST:
            x, y = load_test_data(rst)
            self.dataset_x = x
            self.dataset_y = y

        else:
            x, y = load_train_data(rst)
            self.dataset_x = x
            self.dataset_y = y

        # Arrange x: channel first
        self.dataset_x = np.transpose(self.dataset_x, axes=(0, 1, 2))
        # Normalize between -1 and 1
        self.dataset_x = (self.dataset_x - 127.5) / 127.5
        self.dataset_x = np.expand_dims(self.dataset_x, axis = -1)

        assert (self.dataset_x.shape[0] == self.dataset_y.shape[0])

        # Compute per class instance count.
        classes = np.unique(self.dataset_y)
        self.classes = classes
        per_class_count = list()
        for c in classes:
            per_class_count.append(np.sum(np.array(self.dataset_y == c)))

        # Prune
        if prune_classes:
            for class_to_prune in range(len(classes)):
                remove_size = prune_classes[class_to_prune]
                all_ids = list(np.arange(len(self.dataset_x)))
                mask = [lc == class_to_prune for lc in self.dataset_y]
                all_ids_c = np.array(all_ids)[mask]
                np.random.shuffle(all_ids_c)
                to_delete  = all_ids_c[:remove_size]
                self.dataset_x = np.delete(self.dataset_x, to_delete, axis=0)
                self.dataset_y = np.delete(self.dataset_y, to_delete, axis=0)
                print('Remove {} items in class {}'.format(remove_size, class_to_prune))

        # Recount after pruning
        per_class_count = list()
        for c in classes:
            per_class_count.append(np.sum(np.array(self.dataset_y == c)))
        self.per_class_count = per_class_count

        # List of labels
        self.label_table = [str(c) for c in range(len(self.classes))]

        # Preload all the labels.
        self.labels = self.dataset_y[:]

        # per class ids
        self.per_class_ids = dict()
        ids = np.array(range(len(self.dataset_x)))
        for c in classes:
            self.per_class_ids[c] = ids[self.labels == c]
        self.build_dataset()

    def get_samples_for_class(self, c, samples=None):
        if samples is None:
            samples = self.batch_size

        np.random.shuffle(self.per_class_ids[c])
        to_return = self.per_class_ids[c][0:samples]
        return self.dataset_x[to_return]

    def pair_samples(self, train_x):
        # merge 2 nearest image
        img1 = np.expand_dims(train_x[0], 0)
        img2 = np.expand_dims(train_x[1], 0)
        pair_x = np.array([np.concatenate((img1, img2))])
        for i in range(2, len(train_x) - 1, 2):
            img1 = np.expand_dims(train_x[i], 0)
            img2 = np.expand_dims(train_x[i + 1], 0)
            pair_x = np.concatenate((pair_x, np.expand_dims(
                                    np.concatenate((img1, img2)), 0)))

        return pair_x

    def build_dataset(self):
        qidxs = [[], []]
        train_x, train_y = self.dataset_x, self.dataset_y
        for i in range(2): # 2 classes
            idx = np.where(train_y == i)[0]
            np.random.shuffle(idx)
            qidxs[i] = idx

        q_idx = np.concatenate(qidxs)

        img1 = np.expand_dims(train_x[qidxs[0][0]], 0)
        img2 = np.expand_dims(train_x[qidxs[0][1]], 0)
        pair_x = np.array([np.concatenate((img1, img2))])
        pair_y = [0]
        for i in range(2, len(qidxs[0]) - 1, 2):
            img1 = np.expand_dims(train_x[qidxs[0][i]], 0)
            img2 = np.expand_dims(train_x[qidxs[0][i + 1]], 0)
            pair_x = np.concatenate((pair_x, np.expand_dims(
                np.concatenate((img1, img2)), 0)))

            pair_y.append(0)
        for i in range(0, len(qidxs[1]) - 1, 2):
            img1 = np.expand_dims(train_x[qidxs[1][i]], 0)
            img2 = np.expand_dims(train_x[qidxs[1][i + 1]], 0)
            pair_x = np.concatenate((pair_x, np.expand_dims(
                np.concatenate((img1, img2)), 0)))

            pair_y.append(1)

        pair_y = np.array(pair_y)
        randomize = np.arange(pair_y.shape[0])
        np.random.shuffle(randomize)

        self.pair_x = pair_x[randomize]
        self.pair_y = pair_y[randomize]

    def get_label_table(self):
        return self.label_table

    def get_num_classes(self):
        return len( self.label_table )

    def get_class_probability(self):
        return self.per_class_count/sum(self.per_class_count)

    ### ACCESS DATA AND SHAPES ###
    def get_num_samples(self):
        return self.dataset_x.shape[0]

    def get_image_shape(self):
        return [self.dataset_x.shape[1], self.dataset_x.shape[2], self.dataset_x.shape[3]]

    def next_batch(self):
        dataset_x = self.dataset_x
        labels = self.labels

        indices = np.arange(dataset_x.shape[0])

        np.random.shuffle(indices)

        for start_idx in range(0, dataset_x.shape[0] - self.batch_size + 1, self.batch_size):
            access_pattern = indices[start_idx:start_idx + self.batch_size]
            access_pattern = sorted(access_pattern)

            yield dataset_x[access_pattern, :, :, :], labels[access_pattern]

    def next_pair_batch(self):
        dataset_x = self.pair_x
        labels = self.pair_y

        indices = np.arange(dataset_x.shape[0])

        np.random.shuffle(indices)

        for start_idx in range(0, dataset_x.shape[0] - self.batch_size + 1, self.batch_size):
            access_pattern = indices[start_idx:start_idx + self.batch_size]
            access_pattern = sorted(access_pattern)

            yield dataset_x[access_pattern, :, :, :], labels[access_pattern]

class BalancingGAN:
    def build_res_unet(self):
        def _res_block(x, activation = 'leaky_relu'):
            if activation == 'leaky_relu':
                actv = LeakyReLU()
            else:
                actv = Activation(activation)

            skip = Conv2D(64, 3, strides = 1, padding = 'same')(x)
            out = BatchNormalization()(skip)
            out = actv(out)

            out = Conv2D(64, 3, strides = 1, padding = 'same')(out)
            out = BatchNormalization()(out)
            out = actv(out)

            out = Conv2D(64, 3, strides = 1, padding = 'same')(out)
            out = BatchNormalization()(out)
            out = actv(out)
            out = Add()([out, skip])
            return out


        def _encoder():
            image = Input(shape=(self.resolution, self.resolution, self.channels))

            en_1 = _res_block(image)
            en_1 = Conv2D(64, 3, strides=(2, 2), padding="same")(en_1)
            en_1 = BatchNormalization(momentum = 0.8)(en_1)
            en_1 = LeakyReLU(alpha=0.2)(en_1)
            en_1 = Dropout(0.3)(en_1)
            # out_shape: 32*32*64

            en_2 = _res_block(en_1)
            en_2 = Conv2D(64, 3, strides=(2, 2), padding="same")(en_2)
            en_2 = BatchNormalization()(en_2)
            en_2 = LeakyReLU(alpha=0.2)(en_2)
            en_2 = Dropout(0.3)(en_2)
            # out_shape:  16*16*64

            en_3 = _res_block(en_2)
            en_3 = Conv2D(128, 3, strides = 2, padding = 'same')(en_3)
            en_3 = BatchNormalization(momentum = 0.8)(en_3)
            en_3 = LeakyReLU(alpha=0.2)(en_3)
            en_3 = Dropout(0.3)(en_3)
            # out_shape: 8*8*128

            en_4 = _res_block(en_3)
            en_4 = Conv2D(128, 3, strides = 2, padding = 'same')(en_4)
            en_4 = BatchNormalization(momentum = 0.8)(en_4)
            en_4 = LeakyReLU(alpha=0.2)(en_4)
            en_4 = Dropout(0.3, name = 'decoder_output')(en_4)
            # out_shape: 4*4*128
    
            return Model(inputs = image, outputs = [en_1, en_2, en_3, en_4])

        image = Input(shape=(self.resolution, self.resolution, self.channels))
        latent_code = Input(shape=(4, 4, 128))
        self.encoder = _encoder()
        feature = self.encoder(image)

        # en_1 = Add()([feature[0], external_feature_1])
        # en_2 = Add()([feature[1], external_feature_2])
        # en_3 = Add()([feature[2], external_feature_3])
        en_1 = feature[0]
        en_2 = feature[1]
        en_3 = feature[2]
        en_4 = Add()([feature[3], latent_code])

        de_1 = _res_block(en_4)
        de_1 = Conv2DTranspose(128, 3, strides = 2, padding = 'same')(de_1)
        de_1 = BatchNormalization(momentum = 0.8)(de_1)
        de_1 = Activation('relu')(de_1)
        de_1 = Dropout(0.3)(de_1)
        de_1 = Add()([de_1, en_3])

        de_2 = _res_block(de_1)
        de_2 = Conv2DTranspose(64, 3, strides = 2, padding = 'same')(de_2)
        de_2 = BatchNormalization(momentum = 0.8)(de_2)
        de_2 = Activation('relu')(de_2)
        de_2 = Dropout(0.3)(de_2)
        de_2 = Add()([de_2, en_2])

        de_3 = _res_block(de_2)
        de_3 = Conv2DTranspose(64, 3, strides = 2, padding = 'same')(de_3)
        de_3 = BatchNormalization(momentum = 0.8)(de_3)
        de_3 = Activation('relu')(de_3)
        de_3 = Dropout(0.3)(de_3)
        de_3 = Add()([de_3, en_1])

        de_4 = _res_block(de_3)
        de_4 = Conv2DTranspose(1, 3, strides = 2, padding = 'same')(de_4)
        de_4 = Activation('tanh')(de_4)

        self.generator = Model(
            inputs = [image, latent_code],
            outputs = de_4,
            name='unet'
        )

    def build_image_encoder(self):
        images = Input(shape=(self.resolution, self.resolution, self.channels))

        x = Conv2D(256, kernel_size = 5, strides = 2, padding = 'same', activation = 'relu')(images)
        x = Conv2D(128, kernel_size = 5, strides = 2, padding = 'same', activation = 'relu')(x)
        x = Conv2D(64, kernel_size = 5, strides = 2, padding = 'same', activation = 'relu')(x)
        x = AveragePooling2D(pool_size=(2, 2))(x)
        x = Flatten()(x)
        
        latent_code = Dense(self.latent_size)(x)

        self.image_encoder = Model(inputs  = images, outputs = latent_code, name = 'Image2latent_encoder')

    def build_perceptual_model(self):
        """
        VGG16 model with imagenet weights
        """
        model = VGG16(
            include_top=False,
            weights='imagenet',
            input_tensor = Input(shape=(self.resolution, self.resolution, 3)),
            input_shape = (self.resolution, self.resolution, 3)
        )
        model.trainable = False
        for layer in model.layers:
            layer.trainable = False
        
        self.perceptual_model = model


    def plot_loss_his(self):
        def toarray(lis, k):
            return [d[k] for d in lis]

        def plot_g(train_g, test_g):
            plt.plot(toarray(train_g, 'loss'), label='train_g_loss')
            plt.plot(toarray(train_g, 'loss_from_d'), label='train_g_loss_from_d')
            plt.plot(toarray(train_g, 'fm_loss'), label='train_g_loss_fm')
            plt.plot(toarray(test_g, 'loss'), label='test_g_loss')
            plt.plot(toarray(test_g, 'loss_from_d'), label='test_g_loss_from_d')
            plt.plot(toarray(test_g, 'fm_loss'), label='test_g_loss_fm')
            plt.ylabel('loss')
            plt.xlabel('epoch')
            plt.legend()
            plt.show()

        def plot_d(train_d, test_d):
            plt.plot(train_d, label='train_d_loss')
            plt.plot(test_d, label='test_d_loss')
            plt.ylabel('loss')
            plt.xlabel('epoch')
            plt.legend()
            plt.show()

        train_d = self.train_history['disc_loss']
        train_g = self.train_history['gen_loss']
        test_d = self.test_history['disc_loss']
        test_g = self.test_history['gen_loss']

        if len(train_g) == 0:
            return 

        # plot_g(train_g, test_g)
        plot_d(train_d, test_d)


    def plot_acc_his(self):
        def toarray(lis, k):
            return [d[k] for d in lis]

        def plot_g(train_g, test_g):
            plt.plot(train_g, label='train_g_acc')
            plt.plot(test_g, label='test_g_acc')
            plt.ylabel('acc')
            plt.xlabel('epoch')
            plt.legend()
            plt.show()
        
        def plot_d(train_d, test_d):
            plt.plot(train_d, label='train_d_acc')
            plt.plot(test_d, label='test_d_acc')
            plt.ylabel('acc')
            plt.xlabel('epoch')
            plt.legend()
            plt.show()

        train_d = self.train_history['disc_acc']
        train_g = self.train_history['gen_acc']
        test_d = self.test_history['disc_acc']
        test_g = self.test_history['gen_acc']
        if len(train_g) == 0:
            return
 
        plot_g(train_g, test_g)
        plot_d(train_d, test_d)

    
    def plot_classifier_acc(self):
        plt.plot(self.classifier_acc, label='classifier_acc')
        plt.ylabel('accuracy')
        plt.xlabel('epoch(x5)')
        plt.legend()
        plt.show()

    def _build_common_encoder(self, image, min_latent_res):
        resolution = self.resolution
        channels = self.channels

        # build a relatively standard conv net, with LeakyReLUs as suggested in ACGAN
        cnn = Sequential()

        cnn.add(Conv2D(32, (5, 5), padding='same', strides=(2, 2),
        input_shape=(resolution, resolution,channels)))
        cnn.add(LeakyReLU(alpha=0.2))
        cnn.add(Dropout(0.3))

        size = 128
        cnn.add(Conv2D(size, (5, 5), padding='same', strides=(2, 2)))
        # cnn.add(BatchNormalization())
        cnn.add(LeakyReLU(alpha=0.2))
        cnn.add(Dropout(0.3))

        cnn.add(Conv2D(256, (5, 5), padding='same', strides=(2, 2)))
        # cnn.add(BatchNormalization())
        cnn.add(LeakyReLU(alpha=0.2))
        cnn.add(Dropout(0.3))

        cnn.add(Conv2D(512, (5, 5), padding='same', strides=(2, 2)))
        # cnn.add(BatchNormalization())
        cnn.add(LeakyReLU(alpha=0.2))
        cnn.add(Dropout(0.3))

        cnn.add(Flatten())

        features = cnn(image)
        return features

    def build_discriminator(self, min_latent_res=8):
        resolution = self.resolution
        channels = self.channels

        image = Input(shape=(resolution, resolution,channels))
        noise_image = GaussianNoise(0.1)(image)
        latent = Input(shape=(self.latent_size,))

        features = self._build_common_encoder(noise_image, min_latent_res)
        # Discriminator specific
        features = Dropout(0.4)(features)
        aux = Dense(
            self.nclasses+1, activation='softmax', name='auxiliary'  # nclasses+1. The last class is: FAKE
        )(features)
        self.discriminator = Model(inputs=image, outputs=aux,name='discriminator')

    def generate_latent(self, c, size = 1):
        return np.array([
            np.random.normal(0, 1, 4*4*128).reshape(4,4,128)
            for i in c
        ])


    def discriminate(self, image):
        return self.discriminator(image)

    def features_from_d(self, image):
        return self.features_from_d_model(image)

    def build_latent_encoder(self):
        resolution = self.resolution
        channels = self.channels
        image = Input(shape=(resolution, resolution,channels))
        features = self._build_common_encoder(image, self.min_latent_res)
        # Reconstructor specific
        latent = Dense(100, activation='linear')(features)
        self.latent_encoder = Model(inputs=image, outputs=latent)

    def discriminator_feature_layer(self):
        return self.discriminator.layers[-3]

    def build_features_from_d_model(self):
        image = Input(shape=(self.resolution, self.resolution, self.channels))
        model_output = self.discriminator.layers[-3](image)
        self.features_from_d_model = Model(
            inputs = image,
            output = model_output,
            name = 'Feature_matching'
        )

    def __init__(self, classes, target_class_id,
                # Set dratio_mode, and gratio_mode to 'rebalance' to bias the sampling toward the minority class
                # No relevant difference noted
                dratio_mode="uniform", gratio_mode="uniform",
                adam_lr=0.00005, latent_size=100,
                res_dir = "./res-tmp", image_shape=[3,32,32], min_latent_res=8,
                g_lr = 0.000005):
        self.gratio_mode = gratio_mode
        self.dratio_mode = dratio_mode
        self.classes = classes
        self.target_class_id = target_class_id  # target_class_id is used only during saving, not to overwrite other class results.
        self.nclasses = len(classes)
        self.latent_size = latent_size
        self.res_dir = res_dir
        self.channels = image_shape[-1]
        self.resolution = image_shape[0]
        self.g_lr = g_lr

        self.min_latent_res = min_latent_res
        # Initialize learning variables
        self.adam_lr = adam_lr 
        self.adam_beta_1 = 0.5

        # Initialize stats
        self.train_history = defaultdict(list)
        self.test_history = defaultdict(list)
        self.trained = False

        # Build generator
        # self.build_generator(latent_size, init_resolution=min_latent_res)
        self.build_res_unet()
        self.build_perceptual_model()
        self.build_image_encoder()


        # latent_gen = Input(shape=(latent_size, ))
        latent_code = Input(shape=(4,4,128))

        real_images = Input(shape=(self.resolution, self.resolution, self.channels))

        # Build discriminator
        self.build_discriminator(min_latent_res=min_latent_res)
        self.discriminator.compile(
            optimizer=Adam(lr=self.adam_lr, beta_1=self.adam_beta_1),
            metrics=['accuracy'],
            loss='sparse_categorical_crossentropy'
        )

        # Define combined for training generator.
        fake = self.generator([
            real_images, latent_code
        ])

        self.build_features_from_d_model()

        self.discriminator.trainable = False
        self.generator.trainable = True
        self.features_from_d_model.trainable = False

        aux = self.discriminate(fake)
        img_latent = self.encoder(real_images)[-1]

        # fake info
        fake_features = self.features_from_d(fake)
        fake_perceptual_features = self.perceptual_model(
            Concatenate()([fake, fake, fake])
        )
        # real info
        real_features = self.features_from_d(real_images)
        real_perceptual_features = self.perceptual_model(
            Concatenate()([real_images, real_images, real_images])
        )

        # l1_distance = K.mean(K.abs(img_latent - latent_code))
        # cosine_sim = cosine_similarity(img_latent, latent_code)

        self.combined = Model(
            inputs=[real_images, latent_code],
            outputs=[aux],
            name = 'Combined'
        )

        # perceptual loss
        perceptual_loss =  K.mean(K.abs(
            K.sum(latent_code) * fake_perceptual_features - K.sum(img_latent) * real_perceptual_features
        ))

        fm_loss = K.mean(K.abs(
            K.sum(img_latent) * real_features - K.sum(latent_code) * fake_features
        ))

        self.combined.add_loss(perceptual_loss)
        self.combined.add_loss(fm_loss)

        self.combined.compile(
            optimizer=Adam(
                lr=self.g_lr,
                beta_1=self.adam_beta_1
            ),
            metrics=['accuracy'],
            loss= ['sparse_categorical_crossentropy'],
            # loss_weights = [1.0, 1.0, 0.0],
        )

    def _biased_sample_labels(self, samples, target_distribution="uniform"):
        all_labels = np.full(samples, 0)
        splited = np.array_split(all_labels, self.nclasses)
        all_labels = np.concatenate(
            [
                np.full(splited[classid].shape[0], classid) \
                for classid in range(self.nclasses)
            ]
        )
        np.random.shuffle(all_labels)
        return all_labels

        distribution = self.class_uratio
        if target_distribution == "d":
            distribution = self.class_dratio
        elif target_distribution == "g":
            distribution = self.class_gratio
            
        sampled_labels = np.full(samples,0)
        sampled_labels_p = np.random.normal(0, 1, samples)
        for c in list(range(self.nclasses)):
            mask = np.logical_and((sampled_labels_p > 0), (sampled_labels_p <= distribution[c]))
            sampled_labels[mask] = self.classes[c]
            sampled_labels_p = sampled_labels_p - distribution[c]

        return sampled_labels

    def get_pair_features(self, image_batch):
        # features = np.array([np.average(self.features_from_d_model.predict(pair_x), axis = 0)
        #             for pair_x in image_batch])
        
        # p_features = np.array([
        #     np.average(self.perceptual_model.predict(triple_channels(pair_x)), axis = 0)
        #             for pair_x in image_batch
        # ])
        features = self.features_from_d_model.predict(image_batch)
        p_features = self.perceptual_model.predict(triple_channels(image_batch))

        return features, p_features

    def _train_one_epoch(self, bg_train, from_p = False):
        epoch_disc_loss = []
        epoch_gen_loss = []
        epoch_disc_acc = []
        epoch_gen_acc = []

        for image_batch, label_batch in bg_train.next_batch():
            crt_batch_size = label_batch.shape[0]

            ################## Train Discriminator ##################
            f = self.generate_features(
                                self._biased_sample_labels(crt_batch_size),
                                from_p = from_p
                            )
            generated_images = self.generator.predict(
                [
                    image_batch,
                    f,
                ],
                verbose=0
            )
    
            X = np.concatenate((image_batch, generated_images))
            aux_y = np.concatenate((label_batch, np.full(generated_images.shape[0] , self.nclasses )), axis=0)
            
            X, aux_y = self.shuffle_data(X, aux_y)
            loss, acc = self.discriminator.train_on_batch(X, aux_y)
            epoch_disc_loss.append(loss)
            epoch_disc_acc.append(acc)

            ################## Train Generator ##################
            # fimage_batch, _ = self.shuffle_data(image_batch, image_batch)
            # real_features = self.features_from_d_model.predict(image_batch)
            # perceptual_features = self.perceptual_model.predict(triple_channels(image_batch))

            # real_features, perceptual_features = self.get_pair_features(image_batch)

            f = self.generate_features(
                                self._biased_sample_labels(crt_batch_size),
                                from_p = from_p
                            )

            loss, acc = self.combined.train_on_batch(
                [image_batch, f],
                [label_batch]
            )

            epoch_gen_loss.append(loss)
            epoch_gen_acc.append(acc)

        # epoch_gen_loss_cal = {
        #     'loss': np.mean(np.array([e['loss'] for e in epoch_gen_loss])),
        #     'loss_from_d': np.mean(np.array([e['loss_from_d'] for e in epoch_gen_loss])),
        #     'fm_loss': np.mean(np.array([e['fm_loss'] for e in epoch_gen_loss]))
        # }

        return (
            np.mean(np.array(epoch_disc_loss), axis=0),
            np.mean(np.array(epoch_gen_loss), axis=0),
            np.mean(np.array(epoch_disc_acc), axis=0),
            np.mean(np.array(epoch_gen_acc), axis=0),
        )

    def shuffle_data(self, data_x, data_y):
        rd_idx = np.arange(data_x.shape[0])
        np.random.shuffle(rd_idx)
        return data_x[rd_idx], data_y[rd_idx]

    def _set_class_ratios(self):
        self.class_dratio = np.full(self.nclasses, 0.0)
        # Set uniform
        target = 1/self.nclasses
        self.class_uratio = np.full(self.nclasses, target)
        
        # Set gratio
        self.class_gratio = np.full(self.nclasses, 0.0)
        for c in range(self.nclasses):
            if self.gratio_mode == "uniform":
                self.class_gratio[c] = target
            elif self.gratio_mode == "rebalance":
                self.class_gratio[c] = 2 * target - self.class_aratio[c]
            else:
                print("Error while training bgan, unknown gmode " + self.gratio_mode)
                exit()
                
        # Set dratio
        self.class_dratio = np.full(self.nclasses, 0.0)
        for c in range(self.nclasses):
            if self.dratio_mode == "uniform":
                self.class_dratio[c] = target
            elif self.dratio_mode == "rebalance":
                self.class_dratio[c] = 2 * target - self.class_aratio[c]
            else:
                print("Error while training bgan, unknown dmode " + self.dratio_mode)
                exit()

        # if very unbalanced, the gratio might be negative for some classes.
        # In this case, we adjust..
        if self.gratio_mode == "rebalance":
            self.class_gratio[self.class_gratio < 0] = 0
            self.class_gratio = self.class_gratio / sum(self.class_gratio)
            
        # if very unbalanced, the dratio might be negative for some classes.
        # In this case, we adjust..
        if self.dratio_mode == "rebalance":
            self.class_dratio[self.class_dratio < 0] = 0
            self.class_dratio = self.class_dratio / sum(self.class_dratio)

    def cal_multivariate(self, bg_train):
        print("GAN: computing multivariate")
        # 3 skip-connection and 1 forward connection
        self.covariances = []
        self.means = []

        for c in range(self.nclasses):
            imgs = bg_train.dataset_x[bg_train.per_class_ids[c]]
            feature = self.encoder.predict(imgs)
            feature = feature.reshape(4*4*128, imgs.shape[0])
            self.covariances.append(np.cov(np.transpose()))
            self.means.append(np.mean(feature[i], axis=0))

        self.covariances = np.array(self.covariances)
        self.means = np.array(self.means)

    @staticmethod
    def _reshape(feature):
        return feature.reshape(4, 4, 128),

    def generate_features(self, c, from_p = False):
        """
        from_p: from a distribution
        """

        if not from_p:
            return self.generate_latent(c)

        res = np.array([
            self._reshape(
                np.random.multivariate_normal(self.means[e], self.covariances[e])
            )
            for e in c
        ])

        return res


    def _get_lst_bck_name(self, element):
        # Find last bck name
        files = [
            f for f in os.listdir(self.res_dir)
            if re.match(r'bck_c_{}'.format(self.target_class_id) + "_" + element, f)
        ]
        if len(files) > 0:
            fname = files[0]
            e_str = os.path.splitext(fname)[0].split("_")[-1]

            epoch = int(e_str)

            return epoch, fname

        else:
            return 0, None

    def init_gan(self):
        # Find last bck name
        epoch, generator_fname = self._get_lst_bck_name("generator")

        new_e, discriminator_fname = self._get_lst_bck_name("discriminator")
        if new_e != epoch:  # Reload error, restart from scratch
            return 0

        # Load last bck
        try:
            self.generator.load_weights(os.path.join(self.res_dir, generator_fname))
            self.discriminator.load_weights(os.path.join(self.res_dir, discriminator_fname))
            return epoch

        # Return epoch
        except Exception as e:  # Reload error, restart from scratch (the first time we train we pass from here)
            print(str(e))
            return 0

    def backup_point(self, epoch):
        # Remove last bck
        _, old_bck_g = self._get_lst_bck_name("generator")
        _, old_bck_d = self._get_lst_bck_name("discriminator")
        try:
            os.remove(os.path.join(self.res_dir, old_bck_g))
            os.remove(os.path.join(self.res_dir, old_bck_d))
        except:
            pass

        # Bck
        generator_fname = "{}/bck_c_{}_generator_e_{}.h5".format(self.res_dir, self.target_class_id, epoch)
        discriminator_fname = "{}/bck_c_{}_discriminator_e_{}.h5".format(self.res_dir, self.target_class_id, epoch)

        self.generator.save(generator_fname)
        self.discriminator.save(discriminator_fname)
        # pickle_save(self.classifier_acc, CLASSIFIER_DIR + '/acc_array.pkl')

    def evaluate_d(self, test_x, test_y):
        y_pre = self.discriminator.predict(test_x)
        y_pre = np.argmax(y_pre, axis=1)
        cm = metrics.confusion_matrix(y_true=test_y, y_pred=y_pre)  # shape=(12, 12)
        plt.figure()
        plot_confusion_matrix(cm, hide_ticks=True,cmap=plt.cm.Blues)
        plt.show()

    def evaluate_g(self, test_x, test_y):
        y_pre = self.combined.predict(test_x)
        y_pre = np.argmax(y_pre, axis=1)
        cm = metrics.confusion_matrix(y_true=test_y[0], y_pred=y_pre)
        plt.figure()
        plot_confusion_matrix(cm, hide_ticks=True,cmap=plt.cm.Blues)
        plt.show()

    def train(self, bg_train, bg_test, epochs=50, from_p = False):
        if not self.trained:
            self.autoenc_epochs = 100

            # Class actual ratio
            self.class_aratio = bg_train.get_class_probability()

            # Class balancing ratio
            self._set_class_ratios()

            # Initialization
            print("init gan")
            start_e = self.init_gan()
            # self.init_autoenc(bg_train)
            print("gan initialized, start_e: ", start_e)

            crt_c = 0
            act_img_samples = bg_train.get_samples_for_class(crt_c, 10)
            f = self.generate_features(
                                self._biased_sample_labels(10),
                                from_p = from_p
                            )
            img_samples = np.array([
                [
                    act_img_samples,
                    self.generator.predict([
                        act_img_samples,
                        f
                    ]),
                ]
            ])
            for crt_c in range(1, self.nclasses):
                act_img_samples = bg_train.get_samples_for_class(crt_c, 10)
                new_samples = np.array([
                    [
                        act_img_samples,
                        self.generator.predict([
                            act_img_samples,
                            f
                        ]),
                    ]
                ])
                img_samples = np.concatenate((img_samples, new_samples), axis=0)

            print(img_samples.shape)
            show_samples(img_samples)

            # Train
            for e in range(start_e, epochs):
                start_time = datetime.datetime.now()
                print('GAN train epoch: {}/{}'.format(e+1, epochs))
                train_disc_loss, train_gen_loss, train_disc_acc, train_gen_acc = self._train_one_epoch(bg_train)

                # Test: # generate a new batch of noise
                nb_test = bg_test.get_num_samples()
            
                # sample some labels from p_c and generate images from them
                f = self.generate_features(
                                self._biased_sample_labels(bg_test.dataset_x.shape[0]),
                                from_p = from_p
                            )
                generated_images = self.generator.predict(
                    [bg_test.dataset_x, f],
                    verbose=False
                )

                X = np.concatenate((bg_test.dataset_x, generated_images))
                aux_y = np.concatenate((bg_test.dataset_y, np.full(
                    generated_images.shape[0], self.nclasses )), axis=0
                )

                # see if the discriminator can figure itself out...
                test_disc_loss, test_disc_acc = self.discriminator.evaluate(
                    X, aux_y, verbose=False)

                # real_features = self.features_from_d_model.predict(bg_test.dataset_x)
                # perceptual_features = self.perceptual_model.predict(triple_channels(bg_test.dataset_x))
                # real_features, perceptual_features = self.get_pair_features(bg_test.dataset_x)
                f = self.generate_features(
                        self._biased_sample_labels(bg_test.dataset_x.shape[0]),
                        from_p= from_p
                    )

                test_gen_loss, test_gen_acc = self.combined.evaluate(
                    [bg_test.dataset_x, f],
                    [bg_test.dataset_y],
                    verbose = 0
                )

                if e % 25 == 0:
                    self.evaluate_d(X, aux_y)
                    self.evaluate_g(
                        [
                            bg_test.dataset_x,
                            f
                        ],
                        [bg_test.dataset_y]
                    )

                    crt_c = 0
                    act_img_samples = bg_train.get_samples_for_class(crt_c, 10)
                    # batch_1, batch_2 = self.samples_mask(act_img_samples, 2)
                    f = self.generate_features(
                                self._biased_sample_labels(10),
                                from_p = from_p
                            )
                    img_samples = np.array([
                        [
                            act_img_samples,
                            self.generator.predict([
                                act_img_samples,
                                f,
                            ]),
                        ]
                    ])
                    for crt_c in range(1, self.nclasses):
                        act_img_samples = bg_train.get_samples_for_class(crt_c, 10)
                        # batch_1, batch_2 = self.samples_mask(act_img_samples, 2)
                        new_samples = np.array([
                            [
                                act_img_samples,
                                self.generator.predict([
                                   act_img_samples,
                                    f,
                                ]),
                            ]
                        ])
                        img_samples = np.concatenate((img_samples, new_samples), axis=0)

                    show_samples(img_samples)

                    self.plot_loss_his()
                    self.plot_acc_his()

                if e % 100 == 0:
                    self.backup_point(e)

                self.interval_process(e)


                print("D_loss {}, G_loss {}, D_acc {}, G_acc {} - {}".format(
                    train_disc_loss, train_gen_loss, train_disc_acc, train_gen_acc,
                    datetime.datetime.now() - start_time
                ))
                self.train_history['disc_loss'].append(train_disc_loss)
                self.train_history['gen_loss'].append(train_gen_loss)
                self.test_history['disc_loss'].append(test_disc_loss)
                self.test_history['gen_loss'].append(test_gen_loss)
                # accuracy
                self.train_history['disc_acc'].append(train_disc_acc)
                self.train_history['gen_acc'].append(train_gen_acc)
                self.test_history['disc_acc'].append(test_disc_acc)
                self.test_history['gen_acc'].append(test_gen_acc)
                # self.plot_his()

            self.trained = True

    def samples_mask(self, image_batch,k_shot = 2):
        idx = [[] for _ in range(k_shot)]
        for i in range(0, image_batch.shape[0], k_shot):
            for k in range(k_shot):
                idx[k].append(i + k)

        return [image_batch[np.array(mask)] for mask in idx]


    def generate_samples(self, c, samples, bg = None):
        return self.generate(np.full(samples, c), bg)
    
    def interval_process(self, epoch, interval = 20):
        if epoch % interval != 0:
            return
        # do bussiness thing

    def save_history(self, res_dir, class_id):
        if self.trained:
            filename = "{}/class_{}_score.csv".format(res_dir, class_id)
            generator_fname = "{}/class_{}_generator.h5".format(res_dir, class_id)
            discriminator_fname = "{}/class_{}_discriminator.h5".format(res_dir, class_id)
            reconstructor_fname = "{}/class_{}_reconstructor.h5".format(res_dir, class_id)
            with open(filename, 'w') as csvfile:
                fieldnames = [
                    'train_gen_loss', 'train_disc_loss',
                    'test_gen_loss', 'test_disc_loss'
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for e in range(len(self.train_history['gen_loss'])):
                    row = [
                        self.train_history['gen_loss'][e],
                        self.train_history['disc_loss'][e],
                        self.test_history['gen_loss'][e],
                        self.test_history['disc_loss'][e]
                    ]

                    writer.writerow(dict(zip(fieldnames,row)))

            self.generator.save(generator_fname)
            self.discriminator.save(discriminator_fname)
            self.reconstructor.save(reconstructor_fname)

    def load_models(self, fname_generator, fname_discriminator, fname_reconstructor, bg_train=None):
        self.init_autoenc(bg_train, gen_fname=fname_generator, rec_fname=fname_reconstructor)
        self.discriminator.load_weights(fname_discriminator)