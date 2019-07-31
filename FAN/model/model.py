import torch
import torch.nn as nn
import torch.nn.functional as F

from base import BaseModel


class BinActive(torch.autograd.Function):
    """Binarize the input activations and calculate the mean across channel dimension. """
    def forward(self, input):
        self.save_for_backward(input)
        size = input.size()
        mean = torch.mean(input.abs(), 1, keepdim=True)
        input = input.sign()
        return input, mean

    def backward(self, grad_output, grad_output_mean):
        input, = self.saved_tensors
        print(input)
        grad_input = grad_output.clone()
        grad_input[input.ge(1)] = 0
        grad_input[input.le(-1)] = 0
        return grad_input


class BinConv2d(nn.Module):
    def __init__(self, input_channels, output_channels, kernel_size=-1, stride=-1, padding=-1, dropout=0):
        super(BinConv2d, self).__init__()
        self.layer_type = 'BinConv2d'
        self.kernel_size = kernel_size
        self.stride = stride
        self.padding = padding
        self.dropout_ratio = dropout

        self.bn = nn.BatchNorm2d(input_channels, eps=1e-4, momentum=0.1, affine=True)
        self.bn.weight.data = self.bn.weight.data.zero_().add(1.0)
        if dropout != 0:
            self.dropout = nn.Dropout(dropout)
        self.conv = nn.Conv2d(input_channels, output_channels,
                              kernel_size=kernel_size, stride=stride, padding=padding)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.bn(x)
        x, mean = BinActive()(x)
        if self.dropout_ratio != 0:
            x = self.dropout(x)
        x = self.conv(x)
        x = self.relu(x)
        return x


class Bottleneck(nn.Module):
    def __init__(self):
        super(Bottleneck, self).__init__()
        self.binconv1 = BinConv2d(192, 96, kernel_size=3, stride=1, padding=1)
        self.binconv2 = BinConv2d(96, 48, kernel_size=3, stride=1, padding=1)
        self.binconv3 = BinConv2d(48, 48, kernel_size=3, stride=1, padding=1)

    def forward(self, x):
        residual = x

        out1 = self.binconv1(x)
        out2 = self.binconv2(out1)
        out3 = self.binconv3(out2)

        out_concat = torch.cat((out1, out2, out3), 1)
        out = out_concat + residual

        return out


class HourGlass(nn.Module):
    def __init__(self, num_modules, depth, num_features):
        super(HourGlass, self).__init__()
        self.num_modules = num_modules
        self.depth = depth
        self.num_features = num_features


class FANModel(BaseModel):
    def __init__(self, num_classes=10):
        super(FANModel, self).__init__()
        self.hg = nn.Sequential(
            nn.Conv2d(1, 10, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm2d(),
            nn.MaxPool2d()
        )
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, num_classes)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


a = Bottleneck()

input = torch.randn(1, 192, 64, 64)
b = a(input)
b.shape
