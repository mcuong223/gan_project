from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Flatten, BatchNormalization
from tensorflow.keras.layers import Conv2D, MaxPool2D
from tensorflow.keras import optimizers
from tensorflow.keras import losses
from tensorflow.keras.engine.topology import Layer
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.regularizers import l2
from tensorflow.keras.layers.advanced_activations import PReLU
from tensorflow.keras import initializers
from tensorflow.keras import backend as K
import numpy as np

### parameters

initial_learning_rate = 1e-3
batch_size = 64
epochs = 50
weight_decay = 0.0005


### prelu

def prelu(x, name='default'):
    if name == 'default':
        return PReLU(alpha_initializer=initializers.Constant(value=0.25))(x)
    else:
        return PReLU(alpha_initializer=initializers.Constant(value=0.25), name=name)(x)


### special layer

class CenterLossLayer(Layer):

    def __init__(self, alpha=0.5, classes=10, dims=2, **kwargs):
        super().__init__(**kwargs)
        self.alpha = alpha
        self.classes = classes
        self.dims = dims

    def build(self, input_shape):
        self.centers = self.add_weight(name='centers',
                                       shape=(self.classes, self.dims),
                                       initializer='uniform',
                                       trainable=False)
        # self.counter = self.add_weight(name='counter',
        #                                shape=(1,),
        #                                initializer='zeros',
        #                                trainable=False)  # just for debugging
        super().build(input_shape)

    def call(self, x, mask=None):
        feature, labels = x

        delta_centers = K.dot(K.transpose(labels), (K.dot(labels, self.centers) - feature))  # 10x2
        center_counts = K.sum(K.transpose(labels), axis=1, keepdims=True) + 1  # 10x1
        delta_centers /= center_counts

        new_centers = self.centers - self.alpha * delta_centers
        self.add_update((self.centers, new_centers), x)

        # self.add_update((self.counter, self.counter + 1), x)

        self.result = feature - K.dot(labels, self.centers)
        self.result = K.sum(self.result ** 2, axis=1, keepdims=True) #/ K.dot(x[1], center_counts)
        return self.result # Nx1

    def compute_output_shape(self, input_shape):
        return K.int_shape(self.result)


### custom loss

def zero_loss(y_true, y_pred):
    return 0.5 * K.sum(y_pred, axis=0)


### model

def feature_extractor(img, labels, classes, dims):
    x = Conv2D(filters=32, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(img)
    x = prelu(x)
    x = Conv2D(filters=32, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x)
    x = MaxPool2D(pool_size=(2, 2), strides=(2, 2), padding='valid')(x)
    #
    x = Conv2D(filters=64, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x)
    x = Conv2D(filters=64, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x)
    x = MaxPool2D(pool_size=(2, 2), strides=(2, 2), padding='valid')(x)
    #
    x = Conv2D(filters=128, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x)
    x = Conv2D(filters=128, kernel_size=(5, 5), strides=(1, 1), padding='same', kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x)
    x = MaxPool2D(pool_size=(2, 2), strides=(2, 2), padding='valid')(x)
    #
    x = Flatten()(x)
    x = Dense(dims, kernel_regularizer=l2(weight_decay))(x)
    x = prelu(x, name='side_out')
    #
    main = Dense(classes, activation='softmax', name='main_out', kernel_regularizer=l2(weight_decay))(x)
    side = CenterLossLayer(alpha=0.5, classes=classes, dims=dims, name='centerlosslayer')([x, labels])
    return main, side

