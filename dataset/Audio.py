import re
import time

import cv2
import librosa
import numpy as np
import matplotlib.pyplot as plt
from scipy.fftpack import dct, idct
import pyaudio
from pylab import mpl

mpl.rcParams["font.sans-serif"] = ["SimHei"]


def get_random_wave(frequency, sr=8000, amplitude=1, initial_phase=0, show_T=1):
    """
    返回对应频率的二维波形
    :param sr: 采样率
    :param frequency: 频率
    :param initial_phase: 初相
    :param amplitude: 振幅
    :param show_T: 显示多少秒对应频率的波形
    :return:
    """
    sampling_rate = sr  # 一个周期采样数（采样率）
    sample = sampling_rate * show_T  # 总采样数
    if frequency == 0:
        return np.array([amplitude] * (sample - 1), np.float64)
    angular_frequency = 2 * np.pi * frequency  # 角频率
    t = np.linspace(0, show_T, sample)  # 时间数组
    t = t[:-1]  # t[-1] 是另一个周期的起点需要去掉
    y = amplitude * np.cos(angular_frequency * t + initial_phase)
    # plt.plot(t, y)
    # plt.show()
    return y


def get_y3(frequencys: list, sr=8000, amplitude=None, initial_phase=None, show_T=1):
    """
    获取多个频率组合成的一维信号
    :param frequencys: 需要的频率数组
    :param sr: 采样率
    :param amplitude:
    :param initial_phase:
    :param show_T:
    :return: 多个频率组合成的一维信号
    """
    if amplitude is None:
        amplitude = [1] * len(frequencys)
    if initial_phase is None:
        initial_phase = [0] * len(frequencys)
    y = np.zeros_like(get_random_wave(0, sr=sr))
    for i, frequency in enumerate(frequencys):
        y += get_random_wave(frequency, sr=sr, amplitude=amplitude[i], initial_phase=initial_phase[i], show_T=show_T)
    return y


class Audio(object):
    def __init__(self):
        pass

    def get_cepstrum(self, frames, cep_num=22, filters_num=25, n=2000, L=22, appendEnergy=False):
        """
        得到倒谱
        :param frames:
        :param cep_num:
        :param filters_num:
        :param n:
        :param L:
        :param appendEnergy:
        :return:
        """
        NFFT = 2 * n
        spec_power = 1.0 / NFFT * np.square(frames)  # 功率谱等于每一点的幅度平方/NFFT
        energy = np.sum(spec_power, 1)  # 对每一帧的能量谱进行求和
        energy = np.where(energy == 0, np.finfo(float).eps, energy)
        fb = self.get_filter_banks(filters_num=filters_num).T  # 获得每一个滤波器的频率宽度
        feat = np.dot(spec_power, fb)  # 对滤波器和能量谱进行点乘
        feat = np.where(feat == 0, np.finfo(float).eps, feat)  # 同样不能出现0

        feat = np.log(feat)
        feat_dct_25 = dct(feat, type=2, axis=1, norm='ortho')  # 进行离散余弦变换,只取前22个系数
        feat_dct_22 = feat_dct_25[:, :cep_num]

        feat = self.lifter(feat_dct_22, L)

        if appendEnergy:
            feat[:, 0] = np.log(energy)  # 只取2-13个系数，第一个用能量的对数来代替
        return feat

    def lifter(self, cepstra, L=22):
        """
        将倒谱的22个系数乘以sin(r) r[0,pi], 即将中间放大
        :param cepstra:
        :param L:
        :return:
        """
        if L > 0:
            nframes, ncoeff = np.shape(cepstra)
            n = np.arange(ncoeff)
            lift = 1 + (L / 2) * np.sin(np.pi * n / L)
            res = lift * cepstra
            return res
        else:
            return cepstra

    def derivate(self, feat, big_theta=2):
        """
        计算离散序列的差分（导数）
        :param feat: 倒谱系数
        :param big_theta: 公式中的theta，默认取2
        :return:
        """
        denominator = 0  # 分母
        for theta in np.arange(1, big_theta + 1):
            denominator += theta ** 2
        denominator = denominator * 2  # 计算得到分母的值

        feat_pad = np.zeros((feat.shape[0], feat.shape[1] + big_theta * 2))
        feat_pad[:, big_theta:-big_theta] = feat
        feat_pad[:, :big_theta] = feat[:, :big_theta][:, ::-1]
        feat_pad[:, -big_theta:] = feat[:, -big_theta:][:, ::-1]
        interval_i = 0
        for i in np.arange(1, big_theta + 1):
            interval_i += (feat_pad[:, big_theta + i:-big_theta + i if (-big_theta + i != 0) else None] - feat_pad[:,
                                                                                                          big_theta - i:-big_theta - i if (
                                                                                                                  -big_theta - i != 0) else None]) * i
        result = interval_i / denominator
        return result

    def spectrogramToCepstrum(self, amp_spectrum, cep_num=22, filters_num=25, n=2000, L=22,
                              appendEnergy=False, n_derived=0):
        """
        语谱图转倒谱图
        :param amp_spectrum:
        :param cep_num:
        :param filters_num:
        :param n:
        :param L:
        :param appendEnergy:
        :param n_derived:
        :return:
        """
        mfcc_feat = self.get_cepstrum(amp_spectrum, cep_num=cep_num, filters_num=filters_num, n=n,
                                      L=L,
                                      appendEnergy=appendEnergy)
        # mfcc_feat = np.absolute(mfcc_feat) #不能取绝对值
        ceps = mfcc_feat[:, 1:7]
        one_derived, two_derived = None, None
        if n_derived > 0:
            one_derived = self.derivate(ceps)
        if n_derived > 1:
            two_derived = self.derivate(one_derived)

        return mfcc_feat, one_derived, two_derived

    def refactor_signal(self, frames):
        frames = get_y3([0, 50, 75], sr=200, amplitude=[2, 3, 1.5], initial_phase=[0 * np.pi / 180, -30 * np.pi / 180, 90 * np.pi / 180])
        frames = np.tile(frames.reshape((1, -1)), [10, 1])
        spectrogram = np.fft.fft(frames, n=None)
        amp_spectrum = np.absolute(spectrogram)
        amp_spectrum = np.concatenate(((amp_spectrum / frames.shape[1])[:, :1],
                                       (amp_spectrum / (frames.shape[1] / 2))[:, 1:]), axis=1)
        phase = np.angle(spectrogram)
        frame_num, max_frequency = amp_spectrum.shape
        frame_num, frame_len = frames.shape
        recovery_frames = np.zeros_like(frames)
        recovery_frames1 = np.zeros_like(frames)
        ts = np.linspace(0, 1, frame_len)
        fig, axes = plt.subplots(25, 1, figsize=(8, 25 * 3))
        for num in range(1, 5):
            s = time.time()
            for i, frequency in enumerate(range(max_frequency)):
                y_ = amp_spectrum[num][frequency] * np.cos(2 * np.pi * frequency * ts + phase[num][frequency])
                recovery_frames[num] += y_
                g = 8
                if i % g == 0:
                    diff = np.mean(np.abs(recovery_frames[num]-frames[num]))*1000
                    axes[i // g].plot(ts[:100], frames[num][:100], label=f"原始波形{diff}")
                    axes[i // g].plot(ts[:100], recovery_frames[num][:100], label=f"还原波形{frequency}")
                    axes[i // g].legend()
            plt.show()
            e = time.time()
            print(e - s)
            # recovery_frames1[num] = np.sum(amp_spectrum[num].reshape((1, -1)) * np.cos(
            #     2 * np.pi * np.arange(0, int(max_frequency/2)).reshape((1, -1)) * ts.reshape((-1, 1)) + phase[num].reshape(
            #         (1, -1))), axis=1)
            print(time.time() - e)
            plt.plot(recovery_frames[num][:100], lw=4, color="red")
            # plt.plot(recovery_frames1[num][:100], lw=2, color="green")
            plt.plot(frames[num][:100], lw=1)
            plt.show()
        print(" dsdsdsdsd")
        a = frames - recovery_frames

    def audioToSpectrogram(self, frames, n=None):
        """
        音频信号转为语谱图
        :param n:
        :param frames:
        :return:
        """
        complex_spectrum = np.fft.rfft(frames, n=None)
        amp_spectrum = np.absolute(complex_spectrum)
        amp_spectrum = np.concatenate(((amp_spectrum / frames.shape[1])[:, :1],
                                       (amp_spectrum / (frames.shape[1] / 2))[:, 1:]), axis=1)
        phase = np.angle(complex_spectrum)

        signal = self.refactor_signal(frames)

        spec = np.log1p(amp_spectrum)
        return amp_spectrum, spec, phase

    def spectrogramToAudio(self, spectrogram, phase=None, frame_len=80):
        """
        语谱图转语音
        :param spectrogram: 语谱图
        :param phase: 音频相位信息
        :param frame_len:
        :return:
        """
        wave_data = []
        if phase is not None:
            spec = spectrogram
            pha = phase
            # cv2.imshow("1", spec / spec.max())
            # cv2.waitKey(1)
            amp = np.expm1(spec)  # 振幅
            spec_complex = amp * np.exp(1j * pha)  # 语谱图(复数)
            audio1 = np.fft.irfft(spec_complex)
            # a = audio1[100, :frame_len]
            # plt.plot(a)
            # plt.show()
            # audio = np.reshape(audio1[:, :frame_len], (-1,))
            audio = audio1[:, :frame_len]
            wave_data = self.restoreAudio(audio)
        return wave_data

    def restoreAudio(self, audio_fream):
        amp = 0.9 / max(np.abs(audio_fream.max()), np.abs(audio_fream.min()))
        wave_data = np.asarray(audio_fream * 32768 * amp, np.short)
        wave_data = np.maximum(np.minimum(wave_data, 32767), -32768)
        wave_data = wave_data[:, int(wave_data.shape[1] / 4):int(wave_data.shape[1] * 3 / 4)]
        wave_data = np.reshape(wave_data, (-1))
        return wave_data

    def spectrogramToBark(self, spec, samplerate=16000, filters_num=22, n=2000):
        """
        语谱图转bark域
        :param spec:
        :param band:
        :param reverse:
        :return:
        """
        fb = self.get_filter_banks(filters_num, n=n, samplerate=samplerate, filter=1).T
        a = np.sum(fb, axis=1)
        b = np.sum(fb, axis=0)
        bark = np.dot(spec, fb)
        a = spec.max()
        # bark = bark/bark.max()*spec.max()
        # cv2.imshow("spec", spec/spec.max())
        fb = self.get_filter_banks(filters_num, n=n, samplerate=samplerate, filter=1).T
        hz = np.dot(bark, fb.T)
        # cv2.imshow("hz", hz / hz.max())
        # cv2.waitKey(1)
        b = hz.max()
        return bark

    def barkToSpectrogram(self, bark, samplerate=16000, filters_num=22, n=2000):
        """
        bark域转语谱图
        :param spec:
        :param band:
        :param reverse:
        :return:
        """
        fb = self.get_filter_banks(filters_num, n=n, samplerate=samplerate, filter=1).T
        hz = np.dot(bark, fb.T)
        # cv2.imshow("hz", hz / hz.max())

        return hz

    def get_filter_banks(self, filters_num=22, n=2000, samplerate=16000, low_freq=np.finfo(float).eps,
                         high_freq=None, filter=1):
        '''计算梅尔三角间距滤波器，该滤波器在第一个频率和第三个频率处为0，在第二个频率处为1
        参数说明：
        filers_num:滤波器个数
        NFFT:FFT大小
        samplerate:采样频率
        low_freq:最低频率
        high_freq:最高频率
        '''
        NFFT = 2 * n
        # 首先，将频率hz转化为梅尔频率，因为人耳分辨声音的大小与频率并非线性正比，所以化为梅尔频率再线性分隔
        high_freq = high_freq or samplerate / 2  # 计算音频样本的最大频率
        low_mel = self.hz2bark(low_freq)
        high_mel = self.hz2bark(high_freq)
        # 需要在low_mel和high_mel之间等间距插入filters_num个点，一共filters_num+2个点
        mel_points = np.linspace(low_mel, high_mel, filters_num + 2)
        # 再将梅尔频率转化为hz频率，并且找到对应的hz位置
        hz_points = self.bark2hz(mel_points)
        # 我们现在需要知道这些hz_points对应到fft中的位置
        bin = np.floor((NFFT + 1) * hz_points / samplerate)
        # 接下来建立滤波器的表达式了，每个滤波器在第一个点处和第三个点处均为0，中间为三角形形状
        fbank = np.zeros([filters_num, int(NFFT / 2 + 1)])

        if filter == 0:  # 转为bark域时使用
            #############################
            # 矩形等面积滤波器(平均值滤波) #
            #############################
            for j in range(0, filters_num):
                height = 1 / (int(bin[j + 2]) - int(bin[j]))
                fbank[j, int(bin[j]):int(bin[j + 2])] = height
        elif filter == 1:  # 转为spec时使用
            for j in range(0, filters_num):
                height = 1 / (int(bin[j + 2]) - int(bin[j]))
                for i in range(int(bin[j]), int(bin[j + 1])):
                    fbank[j, i] = (i - bin[j]) / (bin[j + 1] - bin[j]) * height
                for i in range(int(bin[j + 1]), int(bin[j + 2])):
                    fbank[j, i] = (bin[j + 2] - i) / (bin[j + 2] - bin[j + 1]) * height

        ################
        # 余弦三角滤波器 #
        ################
        # for j in range(0, filters_num):
        #     height = 1 / (int(bin[j + 2]) - int(bin[j]))
        #     for i in range(int(bin[j]), int(bin[j + 1])):
        #         fbank[j, i] = (np.cos(((i - bin[j]) / (bin[j + 1] - bin[j])) * np.pi/2 + np.pi)+1)*height
        #     for i in range(int(bin[j + 1]), int(bin[j + 2])):
        #         fbank[j, i] = (np.cos(((i - bin[j+1]) / (bin[j + 2] - bin[j+1])) * np.pi/2 + (np.pi/2))+1)*height

        ################
        # 等高三角滤波器 #
        ################
        # for j in range(0, filters_num):
        #     for i in range(int(bin[j]), int(bin[j + 1])):
        #         fbank[j, i] = (i - bin[j]) / (bin[j + 1] - bin[j])
        #     for i in range(int(bin[j + 1]), int(bin[j + 2])):
        #         fbank[j, i] = (bin[j + 2] - i) / (bin[j + 2] - bin[j + 1])

        ##################
        # 等面积三角滤波器 #
        ##################
        # for j in range(0, filters_num):
        #     height = 1/(int(bin[j + 2]) - int(bin[j]))
        #     for i in range(int(bin[j]), int(bin[j + 1])):
        #         fbank[j, i] = (i - bin[j]) / (bin[j + 1] - bin[j]) * height
        #     for i in range(int(bin[j + 1]), int(bin[j + 2])):
        #         fbank[j, i] = (bin[j + 2] - i) / (bin[j + 2] - bin[j + 1]) * height

        ##################
        # 矩形等面积滤波器 #
        ##################
        # for j in range(0, filters_num):
        #     height = 1 / (int(bin[j + 2]) - int(bin[j]))
        #     fbank[j, int(bin[j]):int(bin[j + 2])] = height

        #################
        # 矩形等高滤波器 #
        #################
        # for j in range(0, filters_num):
        #     fbank[j, int(bin[j]):int(bin[j + 2])] = 0.1

        #############
        # 倒T 滤波器 #
        #############
        # for j in range(0, filters_num):
        #     num = int(bin[j + 1])-int(bin[j])
        #     fbank[j, int(bin[j]):int(bin[j + 1])] = 0.5/num
        #     fbank[j, int(bin[j + 1])] = 1
        #     num = int(bin[j + 2]) - int(bin[j+1])
        #     fbank[j, int(bin[j+1]+1):int(bin[j + 2])] = 0.5 / num
        return fbank

    @staticmethod
    def bark2hz(bark):
        hz = 1960 / ((26.81 / (bark + 0.53)) - 1)
        return hz

    @staticmethod
    def hz2bark(hz):
        bark = 26.81 / (1 + (1960 / hz)) - 0.53
        return bark
